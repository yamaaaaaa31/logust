import sys

from logust import logger

logger.remove()
logger.add(
    sys.stderr,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | "
    "<cyan>{name}</cyan> - {message}",
)

logger.info("Colors in the format")
logger.error("The level tag follows the level color")
