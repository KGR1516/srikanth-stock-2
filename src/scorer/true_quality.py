"""True Quality scoring — multi-factor 0-100 score with penalties.

Dimensions & max weights (from README):
  entry_checks 25 | rsi_health 20 | proximity 20 | liquidity 15
  live_status 15  | volume 5      | catalyst 5
Penalties: loss-making -8, failed breakout -15.
"""
from __future__ import annotations

import pandas as pd

from config import settings


def _scale(value: float, lo: float, hi: float) -> float:
    """Linearly map value in [lo, hi] to [0, 1], clamped."""
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _entry_checks(row: pd.Series) -> float:
    """4-check rule: near level, RSI ok, liquid, not penny → 0..25."""
    checks = [row["near_level"], row["rsi_ok"], row["liquid"], row["not_penny"]]
    passed = sum(bool(c) for c in checks)
    return passed / 4 * settings.WEIGHTS["entry_checks"]


def _trend_alignment(row: pd.Series) -> float:
    """Reward stocks trading above a rising 50/200-EMA structure."""
    if row.get("trend_aligned"):
        frac = 1.0
    elif row["close"] > row.get("ema50", row["close"]):
        frac = 0.4
    else:
        frac = 0.0
    return frac * settings.WEIGHTS["trend_alignment"]


def _momentum(row: pd.Series) -> float:
    """Reward MACD bullish momentum confirmed by ADX trend strength."""
    macd_ok = row.get("macd_hist", 0) > 0
    adx_frac = _scale(row.get("adx", 0), settings.MIN_ADX, settings.MIN_ADX + 20)
    frac = (0.5 if macd_ok else 0.0) + 0.5 * adx_frac
    return frac * settings.WEIGHTS["momentum"]


def _rsi_health(row: pd.Series) -> float:
    """Lower RSI = more room. Best around 50-60, worse as it climbs to 75."""
    rsi = row["rsi"]
    # full marks at <=55, zero at >=75
    frac = 1 - _scale(rsi, 55, 75)
    return frac * settings.WEIGHTS["rsi_health"]


def _proximity(row: pd.Series) -> float:
    """Closer to the breakout level = tighter stop. 0% above = best."""
    frac = 1 - _scale(row["pct_above"], 0, settings.MAX_PCT_ABOVE)
    return max(0.0, frac) * settings.WEIGHTS["proximity"]


def _liquidity(row: pd.Series) -> float:
    """Higher turnover = easier exit. Saturates at ~200 cr."""
    frac = _scale(row["turnover_cr"], settings.MIN_TURNOVER_CR, 200)
    return frac * settings.WEIGHTS["liquidity"]


def _live(row: pd.Series) -> float:
    status = row["live_status"]
    frac = {"Held": 1.0, "Slipped": 0.5, "Failed": 0.0}.get(status, 0.3)
    return frac * settings.WEIGHTS["live_status"]


def _volume(row: pd.Series) -> float:
    frac = _scale(row["volume_x"], settings.MIN_VOLUME_X, 10)
    return frac * settings.WEIGHTS["volume"]


def score_row(row: pd.Series) -> dict:
    components = {
        "entry_checks": round(_entry_checks(row), 1),
        "trend_alignment": round(_trend_alignment(row), 1),
        "momentum": round(_momentum(row), 1),
        "rsi_health": round(_rsi_health(row), 1),
        "proximity": round(_proximity(row), 1),
        "liquidity": round(_liquidity(row), 1),
        "live_score": round(_live(row), 1),
        "volume": round(_volume(row), 1),
    }
    raw = sum(components.values())

    penalty = 0
    if row.get("loss_making", False):
        penalty += settings.PENALTY_LOSS_MAKING
    if row["live_status"] == "Failed" or row["setup_type"] == "Failed":
        penalty += settings.PENALTY_FAILED

    final = max(0, min(100, round(raw + penalty)))
    components["penalty"] = penalty
    components["final_score"] = final
    return components


def score(df: pd.DataFrame) -> pd.DataFrame:
    """Add component columns, final_score, action, position_size, and rank."""
    empty_cols = [
        "entry_checks", "trend_alignment", "momentum", "rsi_health", "proximity",
        "liquidity", "live_score", "volume", "penalty", "final_score",
        "action", "position_size", "true_rank",
    ]
    if df.empty:
        df = df.copy()
        for col in empty_cols:
            df[col] = []
        return df

    df = df.copy()
    breakdown = df.apply(score_row, axis=1, result_type="expand")
    df = pd.concat([df, breakdown], axis=1)

    verdicts = df["final_score"].apply(settings.action_for)
    df["action"] = verdicts.apply(lambda t: t[0])
    df["position_size"] = verdicts.apply(lambda t: t[1])

    df = df.sort_values("final_score", ascending=False).reset_index(drop=True)
    df["true_rank"] = df.index + 1
    return df
