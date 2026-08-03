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
import requests
from io import StringIO

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


_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nseindia.com/",
    "Accept": "text/csv,application/csv,*/*",
}

_NSE_EQUITY_LIST_URLS = [
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
]


def _full_nse_universe() -> list[str] | None:
    """Pull the complete list of NSE-listed equities (EQ series) from NSE's
    public archive CSV. This is the 'total NSE' universe rather than a
    single index's constituents. Best-effort: returns None on any failure
    so callers can fall back to a narrower, more reliable universe.
    """
    try:
        session = requests.Session()
        session.headers.update(_NSE_HEADERS)
        session.get("https://www.nseindia.com/", timeout=settings.REQUEST_TIMEOUT)
        for url in _NSE_EQUITY_LIST_URLS:
            try:
                resp = session.get(url, timeout=settings.REQUEST_TIMEOUT)
                if resp.status_code == 200 and len(resp.content) > 5000:
                    df = pd.read_csv(StringIO(resp.text))
                    df.columns = [c.strip() for c in df.columns]
                    if "SERIES" in df.columns:
                        df = df[df["SERIES"].astype(str).str.strip() == "EQ"]
                    syms = df["SYMBOL"].dropna().astype(str).str.strip().tolist()
                    if syms:
                        log.info(f"Fetched {len(syms)} EQ symbols from full NSE equity list ({url})")
                        return syms
            except Exception as e:  # noqa: BLE001
                log.warning(f"Full NSE list fetch failed for {url}: {e}")
    except Exception as e:  # noqa: BLE001
        log.warning(f"Full NSE universe fetch failed ({e}); falling back")
    return None


def get_universe() -> list[str]:
    watchlist = load_watchlist()
    if watchlist:
        return watchlist
    if settings.UNIVERSE_MODE == "FULL_NSE":
        full = _full_nse_universe()
        if full:
            return full
    idx = _index_universe()
    if idx:
        return idx
    log.warning("Falling back to the small hardcoded universe list")
    return _FALLBACK_UNIVERSE


_FUNDAMENTAL_FIELDS = {
    "sector": "sector",
    "industry": "industry",
    "marketCap": "market_cap",
    "trailingPE": "pe_ratio",
    "returnOnEquity": "roe",
    "debtToEquity": "debt_to_equity",
    "earningsGrowth": "earnings_growth",
    "profitMargins": "profit_margin",
}


def _fetch_fundamentals_one(symbol: str) -> dict:
    """Best-effort fundamental snapshot for one symbol (sector, P/E, ROE, etc.)."""
    import yfinance as yf

    row = {"symbol": symbol}
    try:
        ticker = f"{symbol}{settings.YF_SUFFIX}"
        info = yf.Ticker(ticker).get_info()
        for src, dst in _FUNDAMENTAL_FIELDS.items():
            row[dst] = info.get(src)
    except Exception as e:  # noqa: BLE001
        log.debug(f"{symbol}: fundamentals error {e}")
    return row


def fetch_fundamentals(symbols: list[str]) -> pd.DataFrame:
    """Enrich a short candidate list with fundamental data.

    Deliberately NOT run across the full universe (fundamentals lookups are
    slow, one HTTP round-trip per symbol) — callers should pass only the
    top-ranked technical candidates.
    """
    symbols = list(dict.fromkeys(symbols))  # de-dupe, keep order
    if not symbols:
        return pd.DataFrame(columns=["symbol"])
    log.info(f"Fetching fundamentals for {len(symbols)} candidates")
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(8, settings.MAX_WORKERS)) as pool:
        futures = {pool.submit(_fetch_fundamentals_one, s): s for s in symbols}
        for fut in as_completed(futures):
            rows.append(fut.result())
    return pd.DataFrame(rows)

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

    ema20 = indicators.ema(close, settings.EMA_FAST)
    ema50 = indicators.ema(close, settings.EMA_MID)
    ema200 = indicators.ema(close, settings.EMA_SLOW)
    _, _, macd_hist = indicators.macd(
        close, settings.MACD_FAST, settings.MACD_SLOW, settings.MACD_SIGNAL_PERIOD
    )
    adx14 = indicators.adx(df["High"], df["Low"], close, settings.ADX_PERIOD)

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
        "ema20": round(float(ema20.iloc[-1]), 2),
        "ema50": round(float(ema50.iloc[-1]), 2),
        "ema200": round(float(ema200.iloc[-1]), 2) if pd.notna(ema200.iloc[-1]) else round(float(ema50.iloc[-1]), 2),
        "macd_hist": round(float(macd_hist.iloc[-1]), 3),
        "adx": round(float(adx14.iloc[-1]), 1),
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
