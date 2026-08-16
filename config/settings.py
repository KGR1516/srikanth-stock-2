"""Central configuration — all thresholds, weights, and risk parameters.

Values can be overridden via a .env file (see .env.example).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _f(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _i(key: str, default: int) -> int:
    try:
        return int(float(os.getenv(key, default)))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- Screening
MIN_PRICE = _f("MIN_PRICE", 25)
MIN_TURNOVER_CR = _f("MIN_TURNOVER_CR", 5)
MAX_RSI = _f("MAX_RSI", 70)
MAX_PCT_ABOVE = _f("MAX_PCT_ABOVE", 2.0)
MIN_VOLUME_X = _f("MIN_VOLUME_X", 3.0)

BREAKOUT_LOOKBACK = _i("BREAKOUT_LOOKBACK", 60)
HISTORY_DAYS = _i("HISTORY_DAYS", 400)
VOLUME_AVG_WINDOW = _i("VOLUME_AVG_WINDOW", 20)
RSI_PERIOD = _i("RSI_PERIOD", 14)

# ---------------------------------------------------------------- Trend / momentum
EMA_FAST = _i("EMA_FAST", 20)
EMA_MID = _i("EMA_MID", 50)
EMA_SLOW = _i("EMA_SLOW", 200)
MACD_FAST = _i("MACD_FAST", 12)
MACD_SLOW = _i("MACD_SLOW", 26)
MACD_SIGNAL_PERIOD = _i("MACD_SIGNAL_PERIOD", 9)
ADX_PERIOD = _i("ADX_PERIOD", 14)
MIN_ADX = _f("MIN_ADX", 20)
RS_LOOKBACK = _i("RS_LOOKBACK", 20)  # trading days for return comparison vs Nifty

# ---------------------------------------------------------------- Additional indicators
# Informational-only columns (bb_percent, atr_pct, stoch_k, vwap_dist_pct,
# supertrend_dir) computed in nse_fetcher — not wired into scoring/breakout
# classification, so changing these doesn't affect action/score output.
BBANDS_PERIOD = _i("BBANDS_PERIOD", 20)
BBANDS_STD = _f("BBANDS_STD", 2.0)
ATR_PERIOD = _i("ATR_PERIOD", 14)
SUPERTREND_PERIOD = _i("SUPERTREND_PERIOD", 10)
SUPERTREND_MULTIPLIER = _f("SUPERTREND_MULTIPLIER", 3.0)

# ------------------------------------------------------- Full indicator catalogue
# Compute every pandas-ta-classic indicator per symbol and fold the resulting
# directional consensus into the score (see indicators.confluence_signals).
# Costs roughly 0.7s of CPU per symbol; set to 0 to fall back to the individual
# indicators only, in which case the confluence weight is redistributed.
USE_ALL_INDICATORS = _i("USE_ALL_INDICATORS", 1) == 1

# ---------------------------------------------------------------- Risk
STOP_PCT = _f("STOP_PCT", 0.015)
R_R_T1 = _f("R_R_T1", 2.0)
R_R_T2 = _f("R_R_T2", 3.5)

# ---------------------------------------------------------------- Scoring weights (sum = 100)
# Scoring weights, summing to 100. When the full-catalogue confluence signal was
# added, the nine original weights were scaled down proportionally (x0.85) to
# make room for it, so their balance relative to each other is unchanged.
WEIGHTS = {
    "entry_checks": 17,
    "trend_alignment": 9,
    "momentum": 13,
    "rsi_health": 8,
    "proximity": 8,
    "liquidity": 9,
    "live_status": 8,
    "volume": 4,
    "relative_strength": 9,
    "confluence": 15,
}

PENALTY_LOSS_MAKING = -8
PENALTY_FAILED = -15

# ---------------------------------------------------------------- Action bands
ACTION_BANDS = [
    (80, "BUY NOW", "5-7% of capital"),
    (65, "BUY", "3-5% of capital"),
    (50, "WATCH", "Paper trade only"),
    (35, "AVOID", "Do not enter"),
    (0,  "SKIP", "Ignore"),
]

# ---------------------------------------------------------------- Universe / data
NSE_BASE_URL = os.getenv("NSE_BASE_URL", "https://www.nseindia.com")
NIFTY_INDEX = os.getenv("NIFTY_INDEX", "NIFTY 500")
YF_SUFFIX = os.getenv("YF_SUFFIX", ".NS")
UNIVERSE_MODE = os.getenv("UNIVERSE_MODE", "FULL_NSE")  # FULL_NSE | NIFTY_INDEX | WATCHLIST
FUNDAMENTALS_TOP_N = _i("FUNDAMENTALS_TOP_N", 60)
TOP_PICKS_N = _i("TOP_PICKS_N", 10)

# ---------------------------------------------------------------- Fundamental adjustment
FUND_ROE_GOOD = _f("FUND_ROE_GOOD", 20)          # ROE% for full marks
FUND_DEBT_EQUITY_GOOD = _f("FUND_DEBT_EQUITY_GOOD", 50)  # D/E for full marks (lower better)
FUND_GROWTH_GOOD = _f("FUND_GROWTH_GOOD", 15)    # earnings growth % for full marks
FUND_PE_CAUTION = _f("FUND_PE_CAUTION", 60)      # PE above this trims the bonus

WATCHLIST_FILE = BASE_DIR / "data" / "input" / "watchlist.txt"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "data" / "output"))
LOG_DIR = BASE_DIR / "logs"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

REQUEST_TIMEOUT = _i("REQUEST_TIMEOUT", 15)
MAX_WORKERS = _i("MAX_WORKERS", 15)


def action_for(score: float):
    """Return (action, position_size) for a final score."""
    for threshold, action, size in ACTION_BANDS:
        if score >= threshold:
            return action, size
    return "SKIP", "Ignore"
