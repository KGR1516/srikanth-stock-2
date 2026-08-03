"""Breakout detection — classifies each stock into a setup type.

Setup types (from README):
  Strong Fresh : <=1% above level, volume >=5x, RSI < 70
  Fresh        : <=2% above level, volume >=5x, RSI < 70
  Solid        : <=3% above level, volume >=3x, RSI < 75
  Extended     : >5% above level OR RSI >= 75
  Failed       : price fell back below breakout level
"""
from __future__ import annotations

import pandas as pd

from config import settings
from src.utils.logger import log


def _pct_above(close: float, level: float) -> float:
    if level <= 0:
        return 0.0
    return round((close - level) / level * 100, 2)


def classify(row: pd.Series) -> str:
    close = row["close"]
    level = row["breakout_level"]
    pct = row["pct_above"]
    rsi = row["rsi"]
    vol = row["volume_x"]

    if close < level:
        return "Failed"
    if pct > 5 or rsi >= 75:
        return "Extended"
    if pct <= 1 and vol >= 5 and rsi < 70:
        return "Strong Fresh"
    if pct <= 2 and vol >= 5 and rsi < 70:
        return "Fresh"
    if pct <= 3 and vol >= 3 and rsi < 75:
        return "Solid"
    return "Extended"


def _live_status(row: pd.Series) -> str:
    """How the breakout is holding right now."""
    if row["close"] < row["breakout_level"]:
        return "Failed"
    if row["close"] < row["prev_close"]:
        return "Slipped"
    return "Held"


def _follow_through(row: pd.Series) -> str:
    """How much technical confirmation backs this breakout (trend + momentum)."""
    if row["trend_aligned"] and row["momentum_confirmed"]:
        return "Strong"
    if row["trend_aligned"] or row["momentum_confirmed"]:
        return "Partial"
    return "Weak"


def detect_breakouts(df: pd.DataFrame) -> pd.DataFrame:
    """Annotate the snapshot with breakout type, pct_above, and live status."""
    if df.empty:
        return df

    df = df.copy()
    df["pct_above"] = df.apply(
        lambda r: _pct_above(r["close"], r["breakout_level"]), axis=1
    )
    df["setup_type"] = df.apply(classify, axis=1)
    df["live_status"] = df.apply(_live_status, axis=1)

    # basic entry gate flags (used later by the scorer's 4-check rule)
    df["near_level"] = df["pct_above"] <= settings.MAX_PCT_ABOVE
    df["rsi_ok"] = df["rsi"] < settings.MAX_RSI
    df["liquid"] = df["turnover_cr"] >= settings.MIN_TURNOVER_CR
    df["not_penny"] = df["close"] >= settings.MIN_PRICE

    # trend + momentum confirmation (best-indicator follow-through check)
    df["trend_aligned"] = (df["close"] > df["ema50"]) & (df["ema50"] >= df["ema200"])
    df["momentum_confirmed"] = (df["macd_hist"] > 0) & (df["adx"] >= settings.MIN_ADX)
    df["follow_through"] = df.apply(_follow_through, axis=1)

    return df


def screen(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows that clear the hard universe filters (price + liquidity)."""
    if df.empty:
        return df
    log.info(df[["symbol", "close", "turnover_cr", "not_penny"]].to_string())
    kept = df[(df["not_penny"]) & (df["turnover_cr"] >= settings.MIN_TURNOVER_CR)]
    log.info(f"Screen kept {len(kept)}/{len(df)} rows")
    return kept.reset_index(drop=True)
