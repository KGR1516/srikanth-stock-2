"""Load daily OHLCV bars for one NSE symbol, for the calculation-check agents.

Used only by the agents in .claude/agents/ to recompute the scanner's numbers
by hand. It does not touch the scanner's own code path.

Order of sources:
  1. yfinance, the same call nse_fetcher._fetch_one makes.
  2. A CSV at data/input/bars/<SYMBOL>.csv (Date,Open,High,Low,Close,Volume),
     for when Yahoo is unreachable.
  3. With --synthetic (or synthetic=True), a seeded random walk. Numbers from
     this are only good for checking that formulas match, never for a stock.

Usage:
    python scripts/load_bars.py RELIANCE          # prints the last 5 bars
    from scripts.load_bars import load_bars
    df, source = load_bars("RELIANCE")
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402


def _synthetic(n: int = 280, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 500 * np.exp(np.cumsum(rng.normal(0.0008, 0.018, n)))
    open_ = close * (1 + rng.normal(0, 0.006, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.008, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.008, n)))
    vol = rng.integers(200_000, 2_000_000, n).astype(float)
    vol[-1] *= 4  # make the last bar look like a breakout-day spike
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol}, index=idx
    )


def load_bars(symbol: str, synthetic: bool = False) -> tuple[pd.DataFrame, str]:
    """Return (bars, source) with the same cleaning _fetch_one applies."""
    if synthetic:
        return _synthetic(), "synthetic"

    df = None
    source = ""
    try:
        import yfinance as yf

        df = yf.Ticker(f"{symbol}{settings.YF_SUFFIX}").history(
            period=f"{settings.HISTORY_DAYS}d", interval="1d", auto_adjust=False
        )
        source = "yfinance"
    except Exception as exc:  # noqa: BLE001
        print(f"yfinance unavailable ({exc.__class__.__name__}); trying CSV", file=sys.stderr)

    if df is None or df.empty:
        csv = ROOT / "data" / "input" / "bars" / f"{symbol}.csv"
        if not csv.exists():
            raise SystemExit(
                f"No bars for {symbol}: Yahoo unreachable and {csv} missing. "
                "Export daily bars to that CSV, or pass --synthetic to test formulas only."
            )
        df = pd.read_csv(csv, parse_dates=["Date"], index_col="Date")
        source = f"csv:{csv.name}"

    # Same cleaning as nse_fetcher._fetch_one (src/data/nse_fetcher.py:213-214).
    df = df.rename(columns=str.title).dropna(subset=["Close", "Volume"])
    return df, source


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sym = (args[0] if args else "RELIANCE").upper()
    bars, src = load_bars(sym, synthetic="--synthetic" in sys.argv)
    print(f"{sym}: {len(bars)} bars from {src}")
    print(bars.tail(5).round(2).to_string())
