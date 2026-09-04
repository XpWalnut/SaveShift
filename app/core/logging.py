import logging
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
import time
import traceback
from uuid import uuid4

from app.core.config import AppConfig

LOG_FILE = AppConfig.get_logs_directory() / "SaveShift.log"

logging.basicConfig(
    handlers=[RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")],
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [%(threadName)s]: %(message)s",
)

logger = logging.getLogger("SaveShift")


@contextmanager
def diagnostic_operation(name: str):
    """Log fixed operation labels, timing and safe stack locations, never payloads."""
    operation_id = uuid4().hex[:12]
    started = time.monotonic()
    logger.info("operation=%s id=%s started", name, operation_id)
    try:
        yield
    except Exception as error:
        # Exception text, source lines and locals can contain credentials or URLs.
        frames = traceback.extract_tb(error.__traceback__)
        locations = " > ".join(f"{frame.name}:{frame.lineno}" for frame in frames)
        logger.error(
            "operation=%s id=%s failed elapsed=%.2fs error_type=%s stack=%s",
            name, operation_id, time.monotonic() - started,
            type(error).__name__, locations,
        )
        raise
    else:
        logger.info("operation=%s id=%s completed elapsed=%.2fs",
                    name, operation_id, time.monotonic() - started)
