"""Lightweight technical indicators (no TA-Lib dependency)."""
import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def volume_multiple(volume: pd.Series, window: int = 20) -> float:
    """Latest volume divided by trailing average (excluding the latest bar)."""
    if len(volume) < window + 1:
        window = max(1, len(volume) - 1)
    avg = volume.iloc[-(window + 1):-1].mean()
    if not avg or np.isnan(avg):
        return 0.0
    return round(float(volume.iloc[-1] / avg), 2)
