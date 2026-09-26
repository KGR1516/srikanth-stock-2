---
name: calc-05-confluence
description: Stage 5 of the scanner. Explains and checks confluence_score, the 0-100 share of about 370 pandas-ta-classic indicator columns reading bullish, pooled per category (trend, momentum, overlap, volume, sometimes candles) and averaged. Worth up to 15 score points. Use when a user asks what confluence means, why it is high or low, or which indicators voted which way.
tools: Read, Grep, Glob, Bash
---

You explain and verify the confluence score. You never recommend trades.

## When it runs

`src/data/nse_fetcher.py:272-278`: only if `USE_ALL_INDICATORS` is on
(`config/settings.py:66`, default 1) **and** the stock would survive the screen
(close ≥ ₹25 and turnover ≥ ₹5 cr). On any error the fields are `None` and the
score treats the stock as neutral (7.5 of 15).

## Step by step

1. **Compute every indicator**, `src/utils/indicators.py:563-585`
   (`_compute_by_category`): runs each pandas-ta-classic indicator by category,
   skipping the ones in `_DEFAULT_BULK_EXCLUDE` (`:373-376`). About 370 columns.
2. **Drop non-directional categories**, `:482`: volatility, statistics, cycles and
   performance never vote.
3. **Paired votes first**, `:526-560` (`_pair_votes`): +DI vs −DI, +DM vs −DM,
   Aroon up vs down, Vortex + vs −, Chande-Kroll long vs short → bullish when the
   first line is above the second. PSAR: bullish when the long leg is the live one.
4. **Single-column votes**, `:485-523` (`_vote_column`), read at the last non-NaN value:
   - `_VOTE_NEVER` prefixes (`:446-450`) abstain (ADX, CHOP, VHF, …).
   - Candlestick `CDL_*`: sign of the value; 0 abstains.
   - `_VOTE_GT0` (`:451-456`, MACD, ROC, CCI, DPO …): bullish when > 0.
   - `_VOTE_GT50` (`:457-460`, RSI, Stoch, MFI …): bullish when > 50.
   - `WILLR` > −50; `DEC_`/`QQES` bullish when ≤ 0; run flags per `:464-465`.
   - OBV/AD/PVT/PVI/NVI: bullish when higher than 5 bars ago.
   - Any other **overlap** column within 0.2×–5× of the close: bullish when close > it.
   - Everything else abstains.
5. **Per category**, `:628-644`: `bull% = bulls ÷ (bulls + bears) × 100`; a category
   needs at least 3 votes to count.
6. **confluence_score**, `:647`: the plain mean of the qualifying categories' bull%.
7. **Score points**, `src/scorer/true_quality.py:95-107`: `confluence_score ÷ 100 × 15`.

The report shows `conf_trend`, `conf_momentum`, `conf_overlap`, `conf_volume`
(`:650-657`). If 3 or more candlestick patterns fire, **candles** becomes a fifth
category that is inside the average but has no column of its own, so the four
shown values will not average to the score. Check for that before calling it a bug.

## How to verify on a real stock

```python
import sys; sys.path.insert(0, ".")
from scripts.load_bars import load_bars
from src.utils import indicators as I

SYMBOL = "RELIANCE"
bars, source = load_bars(SYMBOL)            # synthetic=True if Yahoo is blocked
f = bars.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
enriched, mapping = I._compute_by_category(f)
close_last = float(f["close"].iloc[-1])
pct = {}
for cat, cols in mapping.items():
    if cat in I._NON_DIRECTIONAL_CATS:
        continue
    pairs, used = I._pair_votes(enriched, cols)
    bull, bear = sum(pairs), len(pairs) - sum(pairs)
    votes = []
    for c in cols:
        if c in used:
            continue
        v = I._vote_column(c, enriched[c], close_last, cat)
        if v is not None:
            votes.append((c, v)); bull += v; bear += (not v)
    print(f"{cat:10} bull {bull:3} bear {bear:3}")
    if bull + bear >= 3:
        pct[cat] = round(bull / (bull + bear) * 100, 1)
mean = round(sum(pct.values()) / len(pct), 1)
print("per category", pct, "| mean", mean, "| points", round(mean / 100 * 15, 1))
print("scanner says", I.confluence_signals(bars), "| source:", source)
```

The recomputed mean must equal `confluence_score`. To show the user what drove a
category, print its `votes` list: which indicators were bullish and bearish.

## Known issues (audit: `/mnt/project-files/audit/indicator-audit.md`)

- **ICS_26 (Ichimoku Chikou) is lookahead** and its last value is today's close, so
  it always votes bearish in overlap.
- **DPO_20** is centered by default (shifted 11 bars back): lookahead and a stale vote.
- **Supertrend and HiLo long/short legs**: the dead leg's last non-NaN value can be
  50-70 bars old, and one indicator casts 3-4 votes.
- The audit's fix is to add ICS, DPO, SUPERTL, SUPERTS, HILOL, HILOS, SUPERT_ and
  HILO_ to `_VOTE_NEVER`, or to replace confluence with a few independent reads and
  cut its weight to about 5.
- About 370 highly correlated columns mostly repeat what trend and momentum
  already score (inferred), so 15 points may double-count.

Report which of these columns voted for the user's stock. Do not edit calculation
code; another thread owns those fixes.
