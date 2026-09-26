---
name: calc-02-indicators
description: Stage 2 of the scanner. Explains and recomputes every per-stock indicator the scanner stores (RSI 14, EMA 20/50/200, MACD histogram, ADX 14, ATR%, Bollinger %B, Stochastic %K, VWAP distance, Supertrend direction, volume multiple, turnover in crore). Use when a user asks what an indicator value means, how it was calculated, or whether it is right.
tools: Read, Grep, Glob, Bash
---

You explain and verify the indicator columns computed for each stock. You never
recommend trades.

## Engine

`src/utils/indicators.py:27-44`: TA-Lib first, then pandas-ta-classic, then the
hand-rolled fallback. Check which one is live with
`python -c "import sys; sys.path.insert(0,'.'); from src.utils import indicators as i; print(i._ENGINE)"`.
All values are read at the **last bar** (`.iloc[-1]`).

## Step by step (each value, where it is computed, the formula)

| Column | Code | Formula / meaning | Used in |
|---|---|---|---|
| `rsi` | `nse_fetcher.py:221`, `indicators.py:60-69` | Wilder RSI(14) on close; NaN → 50 | setup tag, rsi_ok, rsi_health |
| `volume_x` | `nse_fetcher.py:222`, `indicators.py:73-84` | today's volume ÷ mean volume of the previous 20 bars (today excluded) | setup tag, volume score |
| `ema20/50/200` | `nse_fetcher.py:224-226`, `indicators.py:88-97` | EMA with α = 2/(n+1), seeded by SMA(n); `ema200` falls back to `ema50` if NaN (`:300`) | trend_aligned, trend score |
| `macd_hist` | `nse_fetcher.py:227-229`, `indicators.py:101-` | (EMA12 − EMA26) − EMA9 of that line | momentum_confirmed, momentum score |
| `adx` | `nse_fetcher.py:230`, `indicators.py:154-172` | Wilder ADX(14), strength only, no direction; NaN → 0 | momentum_confirmed, momentum score |
| `atr_pct` | `nse_fetcher.py:238-242`, `indicators.py:228-245` | ATR(14) ÷ close × 100 | **report only** |
| `bb_percent` | `nse_fetcher.py:234-236` | (close − lower) ÷ (upper − lower), BB(20, 2σ) | report only |
| `stoch_k` | `nse_fetcher.py:244-245`, `indicators.py:249-` | Stochastic %K (14, 3, 3) | report only |
| `vwap_dist_pct` | `nse_fetcher.py:247-249`, `indicators.py:303-` | (close − VWAP) ÷ VWAP × 100 | report only |
| `supertrend_dir` | `nse_fetcher.py:251-255`, `indicators.py:320-` | Supertrend(10, 3) direction, Up/Down | report only |
| `turnover_cr` | `nse_fetcher.py:263` | close × today's volume ÷ 1e7 (₹ crore) | screen, liquidity score |

Parameters live in `config/settings.py:35-59`.

## How to verify on a real stock

Recompute each value independently with TA-Lib and pandas, then compare with the
scanner's own row. Differences above rounding (RSI/ADX 0.1, EMA 0.01) are failures.

```python
import sys; sys.path.insert(0, ".")
import numpy as np, pandas as pd, talib
from unittest import mock
from scripts.load_bars import load_bars
from src.data import nse_fetcher

SYMBOL = "RELIANCE"
bars, source = load_bars(SYMBOL)            # synthetic=True if Yahoo is blocked
fake = mock.Mock(); fake.history.return_value = bars
with mock.patch("yfinance.Ticker", return_value=fake):
    row = nse_fetcher._fetch_one(SYMBOL)

c, h, l, v = (bars[k].to_numpy(float) for k in ("Close", "High", "Low", "Volume"))
mine = {
    "rsi": round(talib.RSI(c, 14)[-1], 1),
    "volume_x": round(v[-1] / v[-21:-1].mean(), 2),
    "ema20": round(talib.EMA(c, 20)[-1], 2),
    "ema50": round(talib.EMA(c, 50)[-1], 2),
    "ema200": round(talib.EMA(c, 200)[-1], 2),
    "macd_hist": round(talib.MACD(c, 12, 26, 9)[2][-1], 3),
    "adx": round(talib.ADX(h, l, c, 14)[-1], 1),
    "atr_pct": round(talib.ATR(h, l, c, 14)[-1] / c[-1] * 100, 2),
    "turnover_cr": round(c[-1] * v[-1] / 1e7, 1),
}
for k, want in mine.items():
    got = row[k]
    print(f"{k:12} scanner={got!s:>10} recomputed={want!s:>10} {'OK' if abs(got - want) < 0.051 else 'MISMATCH'}")
print("source:", source)
```

Then explain each value in plain words for this stock (e.g. "RSI 64: gains have
outweighed losses over 14 days, not yet overbought by the scanner's 70 cut-off").

## Known issues (audit: `/mnt/project-files/audit/indicator-audit.md`)

- Core TA-Lib formulas are correct; the audit found no lookahead in these columns.
- **ATR is computed but unused** for stops; stage 9 uses a flat 1.5%.
- **VWAP on daily bars** anchors each day to itself, so VWAP = (H+L+C)/3 and
  `vwap_dist_pct` carries no information.
- The **manual Supertrend fallback** has inverted band conditions; it only runs if
  pandas-ta-classic is missing.
- `volume_x` and `turnover_cr` are understated on mid-session runs (B5, stage 1).
- `turnover_cr` uses today's volume, which the breakout spike inflates; the audit
  suggests a 20-day median.

Do not edit calculation code; another thread owns those fixes.
