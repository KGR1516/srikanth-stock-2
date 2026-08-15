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
