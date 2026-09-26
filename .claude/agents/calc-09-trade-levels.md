---
name: calc-09-trade-levels
description: Stage 9 of the scanner. Explains and checks the entry, stop-loss, target 1, target 2, R:R and position-size text the report prints for BUY NOW and BUY rows, and compares the fixed 1.5% stop with the stock's ATR. Use when a user asks how a stop or target was set, or whether it fits the stock's normal daily range.
tools: Read, Grep, Glob, Bash
---

You explain and verify the trade-plan numbers. You never recommend a trade, a stop
or a position size of your own: you show what the scanner printed and how it
compares with the stock's volatility, and the owner decides.

## Step by step

1. **Which rows**, `src/reports/excel_generator.py:97`: only action BUY NOW or BUY.
2. **Levels**, `:36-46` (`_trade_levels`), with `STOP_PCT = 0.015`, `R_R_T1 = 2.0`,
   `R_R_T2 = 3.5` (`config/settings.py:69-71`):
   - entry = today's close (from the scan; on a mid-session run, a live price)
   - stop = round(entry × (1 − 0.015), 2)
   - risk = entry − stop
   - target1 = round(entry + 2.0 × risk, 2)  → about +3.0%
   - target2 = round(entry + 3.5 × risk, 2)  → about +5.25%
   - "R:R" column = 3.5 for every row (it is the setting, not a per-trade calculation)
3. **Position size**, `config/settings.py:94-100`: text from the score band
   (BUY NOW "5-7% of capital", BUY "3-5% of capital"). It does not use the stop
   distance or the stock's volatility.

## How to verify on a real stock

```python
import sys; sys.path.insert(0, ".")
import talib
from scripts.load_bars import load_bars
from src.reports import excel_generator

SYMBOL = "RELIANCE"
bars, source = load_bars(SYMBOL)            # synthetic=True if Yahoo is blocked
c = bars["Close"].to_numpy(float); h = bars["High"].to_numpy(float); l = bars["Low"].to_numpy(float)
entry = round(float(c[-1]), 2)
lv = excel_generator._trade_levels({"close": entry})
stop = round(entry * (1 - 0.015), 2); risk = entry - stop
print("scanner ", lv)
print("by hand ", dict(entry=entry, stop=stop, target1=round(entry + 2 * risk, 2),
                       target2=round(entry + 3.5 * risk, 2)))

atr = float(talib.ATR(h, l, c, 14)[-1])
print(f"ATR14 = {atr:.2f} ({atr / entry * 100:.2f}% of price); stop distance = {risk:.2f} "
      f"= {risk / atr:.2f} ATR | source: {source}")
```

Report the stop distance in ATR units. A stop under about 1 ATR sits inside the
stock's normal daily range (an observation about the numbers, not advice).

For comparison only, the audit's R1 proposal is shown below so the owner can see
both side by side; present it as the audit's suggestion, never as your pick:
- stop = max(breakout_level − 0.5 × ATR, close − 1.5 × ATR)
- size = (capital × 0.75–1%) ÷ (entry − stop)

## Known issues (audit: `/mnt/project-files/audit/indicator-audit.md`)

- **Fixed 1.5% stop.** Typical NSE mid-cap ATR is 2-4% a day, so the stop is often
  inside normal noise, and targets of 3% / 5.25% are small for a 3-20 day hold.
- **ATR is computed (`atr_pct`) but not used** for the stop.
- **Size from score, not risk**: a volatile stock gets the same allocation as a
  quiet one.
- The stop ignores the breakout level, so it can sit above or far below it.

Do not edit calculation code; another thread owns those fixes.
