import sys

from logust import logger

logger.remove()
logger.add(
    sys.stdout,
    level="DEBUG",
    format="stdout | {level:<8} | {message}",
    filter=lambda record: record["level"].no < 30,
)
logger.add(sys.stderr, level="WARNING", format="stderr | {level:<8} | {message}")

logger.debug("Loading plugins")
logger.info("Server ready")
logger.warning("Slow response: {} ms", 1200)
logger.error("Database connection lost")
