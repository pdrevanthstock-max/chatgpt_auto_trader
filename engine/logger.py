"""
Central Logging Module
"""

from pathlib import Path
from loguru import logger

from config.constants import LOG_FOLDER, LOG_FILE

Path(LOG_FOLDER).mkdir(parents=True, exist_ok=True)

logger.remove()

logger.add(
    LOG_FILE,
    rotation="10 MB",
    retention="30 days",
    level="INFO",
    enqueue=True,
)

logger.add(
    sink=lambda msg: print(msg, end=""),
    level="INFO",
)

__all__ = ["logger"]    