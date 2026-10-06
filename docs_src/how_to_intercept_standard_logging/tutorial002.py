import logging
import sys

from logust import logger
from logust.contrib import intercept_logging

logger.remove()
logger.add(sys.stderr, format="{time} | {level:<8} | {message}")

intercept_logging()

logging.getLogger("myapp.db").warning("Slow query: %.2f s", 1.73)
