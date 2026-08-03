"""Fetches the stock universe and 60-day OHLCV history.

Strategy:
  1. Build a universe (watchlist file → nsepython index constituents → fallback list).
  2. Pull daily OHLCV per symbol via yfinance.
  3. Compute derived fields (RSI, volume multiple, turnover).

Network calls are defensive: any single symbol failure is logged and skipped,
so a partial outage never aborts the whole scan.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd

from config import settings
from src.utils.logger import log
from src.utils import indicators

_FALLBACK_UNIVERSE = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC",
    "BHARTIARTL", "LT", "AXISBANK", "KOTAKBANK", "HINDUNILVR", "BAJFINANCE",
    "MARUTI", "SUNPHARMA", "TITAN", "IRCTC", "SWIGGY", "DEVYANI", "BSOFT",
]


def load_watchlist() -> list[str] | None:
    """Read an optional custom watchlist (one symbol per line, # = comment)."""
    path = settings.WATCHLIST_FILE
    if not path.exists():
        return None
    symbols = []
    for line in path.read_text().splitlines():
        line = line.strip().upper()
        if line and not line.startswith("#"):
            symbols.append(line)
    log.info(f"Loaded {len(symbols)} symbols from watchlist")
    return symbols or None


def _index_universe() -> list[str] | None:
    """Try to pull index constituents via nsepython."""
    try:
        from nsepython import nse_get_index_list, nse_get_index_quote  # noqa
        # nsepython APIs vary across versions; keep this best-effort.
        from nsepython import nsefetch  # noqa
        idx = settings.NIFTY_INDEX.replace(" ", "%20")
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={idx}"
        data = nsefetch(url)
        syms = [row["symbol"] for row in data.get("data", []) if row.get("symbol")]
        syms = [s for s in syms if s != settings.NIFTY_INDEX]
        if syms:
            log.info(f"Fetched {len(syms)} constituents from {settings.NIFTY_INDEX}")
            return syms
    except Exception as e:  # noqa: BLE001
        log.warning(f"nsepython universe fetch failed ({e}); using fallback")
    return None


def get_universe() -> list[str]:
    return load_watchlist() or _index_universe() or _FALLBACK_UNIVERSE


def _fetch_one(symbol: str) -> dict | None:
    """Fetch history for a single symbol and compute the per-stock row."""
    import yfinance as yf

    ticker = f"{symbol}{settings.YF_SUFFIX}"
    try:
        df = yf.Ticker(ticker).history(
            period=f"{settings.HISTORY_DAYS}d", interval="1d", auto_adjust=False
        )
    except Exception as e:  # noqa: BLE001
        log.debug(f"{symbol}: history error {e}")
        return None

    if df is None or df.empty or len(df) < 20:
        log.debug(f"{symbol}: insufficient history")
        return None

    df = df.rename(columns=str.title)
    df = df.dropna(subset=["Close", "Volume"])
    if len(df) < 20:
        log.debug(f"{symbol}: insufficient history after dropping NaN rows")
        return None
    close = df["Close"]
    last = close.iloc[-1]

    rsi_series = indicators.rsi(close, settings.RSI_PERIOD)
    vol_x = indicators.volume_multiple(df["Volume"], settings.VOLUME_AVG_WINDOW)

    # breakout level = highest close over the lookback window, excluding today
    lookback = df.iloc[-(settings.BREAKOUT_LOOKBACK + 1):-1]
    if lookback.empty:
        return None
    breakout_level = float(lookback["Close"].max())

    turnover_cr = float(last * df["Volume"].iloc[-1]) / 1e7  # ₹ crore

    return {
        "symbol": symbol,
        "close": round(float(last), 2),
        "prev_close": round(float(close.iloc[-2]), 2),
        "breakout_level": round(breakout_level, 2),
        "rsi": round(float(rsi_series.iloc[-1]), 1),
        "volume_x": vol_x,
        "turnover_cr": round(turnover_cr, 1),
        "high_60d": round(float(lookback["High"].max()), 2),
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def fetch_market_data(symbols: list[str] | None = None) -> pd.DataFrame:
    """Return a DataFrame of per-symbol snapshot rows."""
    symbols = symbols or get_universe()
    log.info(f"Fetching data for {len(symbols)} symbols "
             f"(max_workers={settings.MAX_WORKERS})")

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=settings.MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, s): s for s in symbols}
        for fut in as_completed(futures):
            row = fut.result()
            if row:
                rows.append(row)

    df = pd.DataFrame(rows)
    log.info(f"Got usable data for {len(df)}/{len(symbols)} symbols")
    return df
