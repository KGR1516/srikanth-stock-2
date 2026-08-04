"""Entry point — orchestrates fetch → detect → score → report."""
from __future__ import annotations

import click

from config import settings
from src.data import nse_fetcher
from src.screener import breakout_engine
from src.scorer import true_quality
from src.reports import excel_generator
from src.utils.logger import log


def run_scan(symbols: list[str] | None = None) -> "tuple":
    log.info("=" * 60)
    log.info("Breakout scan starting")

    raw = nse_fetcher.fetch_market_data(symbols)
    if raw.empty:
        log.error("No market data fetched — aborting")
        return None, None

    detected = breakout_engine.detect_breakouts(raw)
    screened = breakout_engine.screen(detected)
    scored = true_quality.score(screened)

    candidates = scored.head(settings.FUNDAMENTALS_TOP_N)["symbol"].tolist()
    fundamentals = nse_fetcher.fetch_fundamentals(candidates)
    if not fundamentals.empty:
        scored = scored.merge(fundamentals, on="symbol", how="left")
        scored = true_quality.apply_fundamental_adjustment(scored)

    report_path = excel_generator.generate_report(scored)
    _print_summary(scored)
    return scored, report_path


def _print_summary(df):
    counts = df["action"].value_counts().to_dict()
    print("\nDAILY BREAKOUT SUMMARY")
    print("=" * 80)
    print(f"Total screened: {len(df)}")
    print(f"BUY NOW: {counts.get('BUY NOW', 0)}")
    print(f"BUY: {counts.get('BUY', 0)}")
    print(f"WATCH: {counts.get('WATCH', 0)}")
    print(f"AVOID: {counts.get('AVOID', 0)}")
    print(f"SKIP: {counts.get('SKIP', 0)}")

    top = df[df["action"].isin(["BUY NOW", "BUY"])].head(5)
    if not top.empty:
        print("\nTOP ACTIONABLE TRADES:")
        cols = ["true_rank", "symbol", "close", "breakout_level", "pct_above",
                "rsi", "volume_x", "turnover_cr", "final_score", "action"]
        print(top[[c for c in cols if c in top.columns]].to_string(index=False))


@click.command()
@click.option("--symbols", "-s", default=None,
              help="Comma-separated symbols to scan instead of the full universe.")
def cli(symbols):
    """Run the breakout scanner once."""
    syms = [s.strip().upper() for s in symbols.split(",")] if symbols else None
    run_scan(syms)


if __name__ == "__main__":
    cli()
"""Entry point — orchestrates fetch → detect → score → report."""
from __future__ import annotations

import click

from config import settings
from src.data import nse_fetcher
from src.screener import breakout_engine
from src.scorer import true_quality
from src.reports import excel_generator
from src.utils.logger import log


def run_scan(symbols: list[str] | None = None) -> "tuple":
    log.info("=" * 60)
    log.info("Breakout scan starting")

    raw = nse_fetcher.fetch_market_data(symbols)
    if raw.empty:
        log.error("No market data fetched — aborting")
        return None, None

    detected = breakout_engine.detect_breakouts(raw)
    screened = breakout_engine.screen(detected)
    scored = true_quality.score(screened)

    candidates = scored.head(settings.FUNDAMENTALS_TOP_N)["symbol"].tolist()
    fundamentals = nse_fetcher.fetch_fundamentals(candidates)
    if not fundamentals.empty:
        scored = scored.merge(fundamentals, on="symbol", how="left")

    report_path = excel_generator.generate_report(scored)
    _print_summary(scored)
    return scored, report_path


def _print_summary(df):
    counts = df["action"].value_counts().to_dict()
    print("\nDAILY BREAKOUT SUMMARY")
    print("=" * 80)
    print(f"Total screened: {len(df)}")
    print(f"BUY NOW: {counts.get('BUY NOW', 0)}")
    print(f"BUY: {counts.get('BUY', 0)}")
    print(f"WATCH: {counts.get('WATCH', 0)}")
    print(f"AVOID: {counts.get('AVOID', 0)}")
    print(f"SKIP: {counts.get('SKIP', 0)}")

    top = df[df["action"].isin(["BUY NOW", "BUY"])].head(5)
    if not top.empty:
        print("\nTOP ACTIONABLE TRADES:")
        cols = ["true_rank", "symbol", "close", "breakout_level", "pct_above",
                "rsi", "volume_x", "turnover_cr", "final_score", "action"]
        print(top[[c for c in cols if c in top.columns]].to_string(index=False))


@click.command()
@click.option("--symbols", "-s", default=None,
              help="Comma-separated symbols to scan instead of the full universe.")
def cli(symbols):
    """Run the breakout scanner once."""
    syms = [s.strip().upper() for s in symbols.split(",")] if symbols else None
    run_scan(syms)


if __name__ == "__main__":
    cli()
