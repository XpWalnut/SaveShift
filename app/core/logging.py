import logging

from app.core.config import AppConfig

LOG_FILE = AppConfig.get_logs_directory() / "SaveShift.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("SaveShift")