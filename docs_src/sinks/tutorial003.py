import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{level:<8} | {message}", colorize=False)

logger.info("No colors, even in a terminal")
