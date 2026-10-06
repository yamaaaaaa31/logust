import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{time:HH:mm:ss} | {level:<8} | {message}")

logger.info("Server starting")
logger.warning("Cache is almost full")
