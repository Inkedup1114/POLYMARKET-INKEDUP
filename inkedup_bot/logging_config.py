import sys
from pathlib import Path

from loguru import logger

LOG_PATH = Path("bot.log")


def setup_logging():
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        enqueue=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <cyan>{message}</cyan>",
    )
    logger.add(
        LOG_PATH,
        level="DEBUG",
        rotation="5 MB",
        retention="7 days",
        compression="gz",
        enqueue=True,
    )
    return logger
