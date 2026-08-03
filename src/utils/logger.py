"""Structured logging via loguru, with a daily rotating file sink."""
import sys
from loguru import logger
from config import settings

settings.LOG_DIR.mkdir(parents=True, exist_ok=True)

logger.remove()
logger.add(
    sys.stderr,
    level=settings.LOG_LEVEL,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
)
logger.add(
    settings.LOG_DIR / "scanner_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="30 days",
    level="DEBUG",
    encoding="utf-8",
)

log = logger
