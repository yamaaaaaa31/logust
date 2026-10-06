import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{time} | {level} | {message}")

logger.info("Server started")
logger.warning("Disk usage is at {}%", 91)
