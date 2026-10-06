import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, serialize=True)

try:
    result = 1 / 0
except ZeroDivisionError:
    logger.exception("Division failed")
