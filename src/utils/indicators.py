"""Technical indicators.

Primary engine: TA-Lib (github.com/TA-Lib/ta-lib-python) — the fast, C-backed
reference implementation.
Secondary engine: pandas-ta-classic (github.com/xgboosted/pandas-ta-classic) —
a pure-Python/pandas implementation, used automatically if TA-Lib isn't
installed (e.g. its C library isn't available on the host).
Fallback: the original hand-rolled pandas/numpy math that shipped with this
repo, used only if neither library is importable, so a fresh checkout never
breaks just because an optional native dependency is missing.

Every public function below keeps its original signature/return shape —
callers (breakout_engine, nse_fetcher, true_quality) don't need to change.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.logger import log

try:
    import talib as _talib
    _ENGINE = "talib"
except ImportError:  # pragma: no cover - depends on host having the C lib
    _talib = None
    try:
        import pandas_ta_classic as _pta
        _ENGINE = "pandas_ta_classic"
    except ImportError:
        _pta = None
        _ENGINE = "manual"

log.debug(f"indicators engine: {_ENGINE}")


# --------------------------------------------------------------------- RSI
def _rsi_manual(close: pd.Series, period: int) -> pd.Series:
    """Wilder's RSI (original hand-rolled implementation, used as last resort)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI, via TA-Lib -> pandas-ta-classic -> manual fallback."""
    if _talib is not None:
        out = pd.Series(_talib.RSI(close.to_numpy(dtype=float), timeperiod=period), index=close.index)
        return out.fillna(50)
    if _pta is not None:
        out = _pta.rsi(close, length=period)
        if out is not None:
            return out.reindex(close.index).fillna(50)
    return _rsi_manual(close, period)


# ------------------------------------------------------------ Volume multiple
def volume_multiple(volume: pd.Series, window: int = 20) -> float:
    """Latest volume divided by trailing average (excluding the latest bar).

    No equivalent built-in in TA-Lib / pandas-ta-classic — kept as the
    original hand-rolled calculation.
    """
    if len(volume) < window + 1:
        window = max(1, len(volume) - 1)
    avg = volume.iloc[-(window + 1):-1].mean()
    if not avg or np.isnan(avg):
        return 0.0
    return round(float(volume.iloc[-1] / avg), 2)


# --------------------------------------------------------------------- EMA
def ema(close: pd.Series, period: int) -> pd.Series:
    """Exponential moving average, via TA-Lib -> pandas-ta-classic -> manual."""
    if _talib is not None:
        out = pd.Series(_talib.EMA(close.to_numpy(dtype=float), timeperiod=period), index=close.index)
        return out
    if _pta is not None:
        out = _pta.ema(close, length=period)
        if out is not None:
            return out.reindex(close.index)
    return close.ewm(span=period, adjust=False, min_periods=period).mean()


# -------------------------------------------------------------------- MACD
def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Classic MACD: returns (macd_line, signal_line, histogram)."""
    if _talib is not None:
        macd_line, signal_line, hist = _talib.MACD(
            close.to_numpy(dtype=float), fastperiod=fast, slowperiod=slow, signalperiod=signal
        )
        return (
            pd.Series(macd_line, index=close.index),
            pd.Series(signal_line, index=close.index),
            pd.Series(hist, index=close.index),
        )
    if _pta is not None:
        out = _pta.macd(close, fast=fast, slow=slow, signal=signal)
        if out is not None and not out.empty:
            cols = list(out.columns)  # [MACD_f_s_sig, MACDh_f_s_sig, MACDs_f_s_sig]
            macd_line = out[cols[0]].reindex(close.index)
            hist = out[cols[1]].reindex(close.index)
            signal_line = out[cols[2]].reindex(close.index)
            return macd_line, signal_line, hist
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


# --------------------------------------------------------------------- ADX
def _adx_manual(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    prev_close = close.shift()
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)

    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * (
        plus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        / atr.replace(0, np.nan)
    )
    minus_di = 100 * (
        minus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        / atr.replace(0, np.nan)
    )

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean().fillna(0)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index — trend strength, 0-100 (direction-agnostic)."""
    if _talib is not None:
        out = pd.Series(
            _talib.ADX(
                high.to_numpy(dtype=float),
                low.to_numpy(dtype=float),
                close.to_numpy(dtype=float),
                timeperiod=period,
            ),
            index=close.index,
        )
        return out.fillna(0)
    if _pta is not None:
        out = _pta.adx(high, low, close, length=period)
        if out is not None and not out.empty:
            col = next((c for c in out.columns if c.startswith("ADX_")), out.columns[0])
            return out[col].reindex(close.index).fillna(0)
    return _adx_manual(high, low, close, period)


# --------------------------------------------------------------------- SMA
def sma(close: pd.Series, period: int = 20) -> pd.Series:
    """Simple moving average, via TA-Lib -> pandas-ta-classic -> manual."""
    if _talib is not None:
        out = pd.Series(_talib.SMA(close.to_numpy(dtype=float), timeperiod=period), index=close.index)
        return out
    if _pta is not None:
        out = _pta.sma(close, length=period)
        if out is not None:
            return out.reindex(close.index)
    return close.rolling(window=period, min_periods=period).mean()


# ----------------------------------------------------------- Bollinger Bands
def bbands(close: pd.Series, period: int = 20, std: float = 2.0):
    """Bollinger Bands: returns (upper, middle, lower)."""
    if _talib is not None:
        upper, middle, lower = _talib.BBANDS(
            close.to_numpy(dtype=float), timeperiod=period, nbdevup=std, nbdevdn=std
        )
        return (
            pd.Series(upper, index=close.index),
            pd.Series(middle, index=close.index),
            pd.Series(lower, index=close.index),
        )
    if _pta is not None:
        out = _pta.bbands(close, length=period, std=std)
        if out is not None and not out.empty:
            lower_col = next((c for c in out.columns if c.startswith("BBL_")), None)
            mid_col = next((c for c in out.columns if c.startswith("BBM_")), None)
            upper_col = next((c for c in out.columns if c.startswith("BBU_")), None)
            if lower_col and mid_col and upper_col:
                return (
                    out[upper_col].reindex(close.index),
                    out[mid_col].reindex(close.index),
                    out[lower_col].reindex(close.index),
                )
    middle = close.rolling(window=period, min_periods=period).mean()
    dev = close.rolling(window=period, min_periods=period).std()
    upper = middle + std * dev
    lower = middle - std * dev
    return upper, middle, lower


# --------------------------------------------------------------------- ATR
def _atr_manual(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift()
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range, via TA-Lib -> pandas-ta-classic -> manual fallback."""
    if _talib is not None:
        out = pd.Series(
            _talib.ATR(
                high.to_numpy(dtype=float),
                low.to_numpy(dtype=float),
                close.to_numpy(dtype=float),
                timeperiod=period,
            ),
            index=close.index,
        )
        return out
    if _pta is not None:
        out = _pta.atr(high, low, close, length=period)
        if out is not None:
            return out.reindex(close.index)
    return _atr_manual(high, low, close, period)


# ---------------------------------------------------------------- Stochastic
def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
    smooth_k: int = 3,
):
    """Stochastic oscillator: returns (%K, %D)."""
    if _talib is not None:
        k, d = _talib.STOCH(
            high.to_numpy(dtype=float),
            low.to_numpy(dtype=float),
            close.to_numpy(dtype=float),
            fastk_period=k_period,
            slowk_period=smooth_k,
            slowk_matype=0,
            slowd_period=d_period,
            slowd_matype=0,
        )
        return pd.Series(k, index=close.index), pd.Series(d, index=close.index)
    if _pta is not None:
        out = _pta.stoch(high, low, close, k=k_period, d=d_period, smooth_k=smooth_k)
        if out is not None and not out.empty:
            k_col = next((c for c in out.columns if c.startswith("STOCHk_")), None)
            d_col = next((c for c in out.columns if c.startswith("STOCHd_")), None)
            if k_col and d_col:
                return out[k_col].reindex(close.index), out[d_col].reindex(close.index)
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()
    raw_k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    k_line = raw_k.rolling(window=smooth_k, min_periods=smooth_k).mean()
    d_line = k_line.rolling(window=d_period, min_periods=d_period).mean()
    return k_line.fillna(50), d_line.fillna(50)


# --------------------------------------------------------------------- OBV
def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume, via TA-Lib -> pandas-ta-classic -> manual fallback."""
    if _talib is not None:
        out = pd.Series(
            _talib.OBV(close.to_numpy(dtype=float), volume.to_numpy(dtype=float)),
            index=close.index,
        )
        return out
    if _pta is not None:
        out = _pta.obv(close, volume)
        if out is not None:
            return out.reindex(close.index)
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


# -------------------------------------------------------------------- VWAP
def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Volume Weighted Average Price (cumulative, session-agnostic).

    No TA-Lib equivalent (VWAP isn't part of TA-Lib) — tries pandas-ta-classic
    first, then falls back to the original hand-rolled calculation.
    """
    if _pta is not None:
        out = _pta.vwap(high, low, close, volume)
        if out is not None:
            return out.reindex(close.index)
    typical_price = (high + low + close) / 3
    cum_vol = volume.cumsum()
    cum_vol_price = (typical_price * volume).cumsum()
    return cum_vol_price / cum_vol.replace(0, np.nan)


# --------------------------------------------------------------- Supertrend
def supertrend(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10, multiplier: float = 3.0
):
    """Supertrend: returns (supertrend_line, direction) where direction is
    1 for an uptrend and -1 for a downtrend.

    No TA-Lib equivalent — tries pandas-ta-classic first, then falls back to
    the original hand-rolled calculation built on the ATR helper above.
    """
    if _pta is not None:
        out = _pta.supertrend(high, low, close, length=period, multiplier=multiplier)
        if out is not None and not out.empty:
            line_col = next((c for c in out.columns if c.startswith("SUPERT_")), None)
            dir_col = next((c for c in out.columns if c.startswith("SUPERTd_")), None)
            if line_col and dir_col:
                return out[line_col].reindex(close.index), out[dir_col].reindex(close.index)

    atr_val = _atr_manual(high, low, close, period)
    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr_val
    lower_band = hl2 - multiplier * atr_val

    final_upper = upper_band.copy()
    final_lower = lower_band.copy()
    direction = pd.Series(1, index=close.index)
    trend = pd.Series(np.nan, index=close.index)

    for i in range(1, len(close)):
        if close.iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = min(upper_band.iloc[i], final_upper.iloc[i - 1])
        else:
            final_upper.iloc[i] = upper_band.iloc[i]

        if close.iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = max(lower_band.iloc[i], final_lower.iloc[i - 1])
        else:
            final_lower.iloc[i] = lower_band.iloc[i]

        if close.iloc[i] > final_upper.iloc[i]:
            direction.iloc[i] = 1
        elif close.iloc[i] < final_lower.iloc[i]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

        trend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

    return trend, direction


# ------------------------------------------------------ All indicators (bulk)
def compute_all_indicators(df: pd.DataFrame, exclude: list[str] | None = None):
    """Compute every indicator pandas-ta-classic ships (224 category
    indicators across Candles, Cycles, Math, Momentum, Overlap, Statistics,
    Trend, Volatility and Volume -- which already includes all 62 native
    candlestick patterns as part of the Candles category) and append them
    all as extra columns.

    Unlike the individual functions above, there is no manual/TA-Lib
    fallback here -- replicating 224+ indicator formulas by hand isn't
    practical. This requires pandas-ta-classic to be installed (see
    requirements.txt); indicators that support it use TA-Lib automatically
    for acceleration when TA-Lib is also installed, same as the rest of
    this module.

    Runs each indicator individually (rather than pandas-ta-classic's own
    ``df.ta.strategy("all")``) so that a bug or edge case in any single
    indicator only skips that one instead of aborting the whole batch --
    skipped indicators are logged, not raised.

    Args:
        df: OHLCV DataFrame with lowercase columns: open, high, low, close,
            volume.
        exclude: extra indicator names to skip, in addition to the ones
            pandas-ta-classic itself excludes by default because they need
            inputs beyond a plain OHLCV frame (comparison/crossover
            signals, custom-length "runs", volume profile, etc.).

    Returns:
        A new DataFrame (the input `df` is left untouched) with every
        successfully computed indicator appended as extra columns.
    """
    if _pta is None:
        raise RuntimeError(
            "compute_all_indicators() requires pandas-ta-classic. "
            "Install it with `pip install pandas-ta-classic` (see requirements.txt)."
        )

    # Same default exclusions pandas-ta-classic's own strategy("all") applies:
    # these need extra non-OHLCV inputs and can't run standalone off a
    # plain price/volume frame.
    default_exclude = {
        "above", "above_value", "below", "below_value", "cross", "cross_value",
        "long_run", "short_run", "td_seq", "tsignals", "vp", "xsignals",
    }
    skip = default_exclude | set(exclude or [])

    out = df.copy()
    names = out.ta.indicators(as_list=True)
    added, skipped = 0, []
    for name in names:
        if name in skip:
            continue
        try:
            getattr(out.ta, name)(append=True)
            added += 1
        except Exception as exc:  # pandas-ta-classic isn't uniformly robust across all 200+ indicators
            skipped.append(name)
            log.debug(f"compute_all_indicators: skipped '{name}' ({exc})")

    log.debug(
        f"compute_all_indicators: {added} indicator(s) computed, "
        f"{len(skipped)} skipped, {out.shape[1] - df.shape[1]} columns added"
    )
    return out
