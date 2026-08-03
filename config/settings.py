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

# ---------------------------------------------------------------- Risk
STOP_PCT = _f("STOP_PCT", 0.015)
R_R_T1 = _f("R_R_T1", 2.0)
R_R_T2 = _f("R_R_T2", 3.5)

# ---------------------------------------------------------------- Scoring weights (sum = 100)
WEIGHTS = {
    "entry_checks": 20,
    "trend_alignment": 15,
    "momentum": 15,
    "rsi_health": 10,
    "proximity": 15,
    "liquidity": 10,
    "live_status": 10,
    "volume": 5,
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
