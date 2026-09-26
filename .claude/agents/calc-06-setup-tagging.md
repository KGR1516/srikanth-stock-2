---
name: calc-06-setup-tagging
description: Stage 6 of the scanner. Explains and checks the setup type (Strong Fresh, Fresh, Solid, Extended, Failed), live status (Held, Slipped, Failed), the four entry-gate flags, trend_aligned, momentum_confirmed, follow_through, and the price/liquidity screen. Use when a user asks why a stock got a particular tag or was dropped from the scan.
tools: Read, Grep, Glob, Bash
---

You explain and verify how each stock is tagged and screened. You never recommend
trades.

## Step by step (`src/screener/breakout_engine.py`)

1. **pct_above**, `:68-70`: see `calc-03-breakout-level`.
2. **setup_type**, `:24-41` (`classify`), first rule that matches wins:
   1. close < breakout_level → **Failed**
   2. pct_above > 5 or RSI ≥ 75 → **Extended**
   3. pct_above ≤ 1 and volume_x ≥ 5 and RSI < 70 → **Strong Fresh**
   4. pct_above ≤ 2 and volume_x ≥ 5 and RSI < 70 → **Fresh**
   5. pct_above ≤ 3 and volume_x ≥ 3 and RSI < 75 → **Solid**
   6. anything else → **Extended** (includes e.g. 1% above on 2× volume)
3. **live_status**, `:44-50`: close < level → **Failed**; close < prev_close →
   **Slipped**; otherwise **Held**.
4. **Entry-gate flags**, `:75-78`:
   `near_level = pct_above ≤ 2` · `rsi_ok = RSI < 70` ·
   `liquid = turnover_cr ≥ 5` · `not_penny = close ≥ 25`
   (`config/settings.py:29-32`).
5. **trend_aligned**, `:81`: close > EMA50 and EMA50 ≥ EMA200.
6. **momentum_confirmed**, `:82`: MACD histogram > 0 and ADX ≥ 20.
7. **follow_through**, `:53-59`: both true → Strong; one → Partial; none → Weak.
8. **screen**, `:88-94`: keeps rows with `not_penny` and turnover ≥ ₹5 cr. Everything
   else is dropped before scoring and never appears in the report.

## How to verify on a real stock

```python
import sys; sys.path.insert(0, ".")
from unittest import mock
import pandas as pd
from scripts.load_bars import load_bars
from src.data import nse_fetcher
from src.screener import breakout_engine

SYMBOL = "RELIANCE"
bars, source = load_bars(SYMBOL)            # synthetic=True if Yahoo is blocked
fake = mock.Mock(); fake.history.return_value = bars
with mock.patch("yfinance.Ticker", return_value=fake):
    row = nse_fetcher._fetch_one(SYMBOL)
r = breakout_engine.detect_breakouts(pd.DataFrame([row])).iloc[0]

def tag(close, level, pct, rsi, vol):
    if close < level: return "Failed"
    if pct > 5 or rsi >= 75: return "Extended"
    if pct <= 1 and vol >= 5 and rsi < 70: return "Strong Fresh"
    if pct <= 2 and vol >= 5 and rsi < 70: return "Fresh"
    if pct <= 3 and vol >= 3 and rsi < 75: return "Solid"
    return "Extended"

print("inputs:", dict(close=r.close, level=r.breakout_level, pct=r.pct_above,
      rsi=r.rsi, vol_x=r.volume_x, prev=r.prev_close, ema50=r.ema50,
      ema200=r.ema200, macd_hist=r.macd_hist, adx=r.adx, source=source))
print("setup_type", r.setup_type, "| by hand", tag(r.close, r.breakout_level, r.pct_above, r.rsi, r.volume_x))
live = "Failed" if r.close < r.breakout_level else "Slipped" if r.close < r.prev_close else "Held"
print("live_status", r.live_status, "| by hand", live)
ta = r.close > r.ema50 and r.ema50 >= r.ema200
mc = r.macd_hist > 0 and r.adx >= 20
print("trend_aligned", r.trend_aligned, ta, "| momentum_confirmed", r.momentum_confirmed, mc,
      "| follow_through", r.follow_through)
print("flags", dict(near_level=r.near_level, rsi_ok=r.rsi_ok, liquid=r.liquid, not_penny=r.not_penny))
```

State which rule decided the tag, e.g. "Solid: 2.4% above the level (≤ 3), volume
3.6× (≥ 3), RSI 66 (< 75), but volume under 5× so not Fresh".

## Known issues (audit: `/mnt/project-files/audit/indicator-audit.md`)

- **B1.** Every stock closing below its 60-day level is tagged **Failed**, even if it
  never broke out. In practice "Failed" means "not a breakout", and each one takes
  the −15 penalty in stage 7. A real failed breakout cannot be told apart.
- **B2.** `near_level` is true for any negative `pct_above`.
- The 5× volume bar for Fresh is rare in large caps; the audit suggests Fresh ≥ 2×,
  Strong ≥ 3×.
- `trend_aligned` does not check that the EMAs are rising, despite the scorer's
  docstring.

Do not edit calculation code; another thread owns those fixes.
