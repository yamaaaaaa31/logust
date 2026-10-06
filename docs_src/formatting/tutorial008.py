import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level} | {message}\n{exception}")

logger.info("Starting the import")
try:
    rows = 100 / 0
except ZeroDivisionError:
    logger.exception("Import failed")
