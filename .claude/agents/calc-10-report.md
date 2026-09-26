---
name: calc-10-report
description: Stage 10 of the scanner. Explains and checks what each sheet of the daily Excel report contains (Master Scan, Actionable Trades, Top Picks, Score Breakdown, Pre-Market Checklist, Summary), how the session label is set, and whether the report's numbers tie back to the scored table. Use when a user asks what a report column means or why two sheets disagree.
tools: Read, Grep, Glob, Bash
---

You explain and verify the Excel report. You never recommend trades.

## Step by step (`src/reports/excel_generator.py`)

1. **File name and session**, `:25-33`, `:78-83`:
   `breakout_scan_<YYYY-MM-DD>_<session>.xlsx` in `data/output/`. Session by IST
   clock at write time: before 09:15 Pre-Market, before 15:30 Mid-Session, else
   Post-Close. The date is the runner's local date.
2. **Master Scan**, `:85-95`: every screened stock, in rank order, with the columns
   in `master_cols`; the action cell is colour-filled (`:14-20`, `:70-75`).
3. **Actionable Trades**, `:97-108`: BUY NOW and BUY rows with entry, stop, targets,
   R:R and position size from `calc-09-trade-levels`.
4. **Top Picks**, `:131-141`: rows that have any fundamental field, top
   `TOP_PICKS_N` (10) by final_score.
5. **Score Breakdown**, `:110-113`: per-factor points from `calc-07-scoring`.
6. **Pre-Market Checklist**, `:115-130`: a fixed 10-item manual checklist.
7. **Summary**, `:143-159`: date, counts per action, top symbol and score, session,
   number of top picks.
8. Delivery: `send_email.py` mails the file from GitHub Actions
   (`.github/workflows/daily-scan.yml`).

## How to verify

Build a report from a known table and tie it back:

```python
import sys; sys.path.insert(0, ".")
from pathlib import Path
from unittest import mock
import pandas as pd
from scripts.load_bars import load_bars
from src.data import nse_fetcher
from src.screener import breakout_engine
from src.scorer import true_quality
from src.reports import excel_generator

rows = []
for i, sym in enumerate(["AAA", "BBB", "CCC"]):          # or real symbols
    bars, _ = load_bars(sym, synthetic=True)               # drop synthetic for real data
    bars = bars.iloc[: len(bars) - 5 * i]                  # vary them a little
    fake = mock.Mock(); fake.history.return_value = bars
    with mock.patch("yfinance.Ticker", return_value=fake):
        rows.append(nse_fetcher._fetch_one(sym))
scored = true_quality.score(breakout_engine.screen(breakout_engine.detect_breakouts(pd.DataFrame(rows))))
path = excel_generator.generate_report(scored, out_dir=Path("/tmp/report-check"))
xl = pd.read_excel(path, sheet_name=None)
print({k: v.shape for k, v in xl.items()})
b = xl["Score Breakdown"]
factor_cols = [c for c in b.columns if c not in ("true_rank", "symbol", "final_score")]
b["sum_shown"] = b[factor_cols].sum(axis=1)
print(b[["symbol", "sum_shown", "final_score"]])
```

Checks to report:
- Master Scan row count = screened count; ranks 1..N with no gaps.
- Actionable Trades rows = count of BUY NOW + BUY in Master Scan.
- Summary counts match `value_counts()` of the action column.
- **Score Breakdown ties to final_score.** It will not today: see below.

## Known issues

- **Score Breakdown is missing `relative_strength`, `confluence` and
  `fundamental_bonus`** (`:110-112`), so its visible factors do not add up to
  `final_score`; up to 24 points plus the bonus are hidden. Found while writing this
  agent, not in the audit.
- The session label comes from the clock when the file is written, not from the
  bar's date, so a delayed run can be mislabelled.
- Mid-session files (B5 in `/mnt/project-files/audit/indicator-audit.md`) are scored
  on an unfinished bar and are not comparable with post-close files.

Do not edit calculation or report code; another thread owns those fixes.
