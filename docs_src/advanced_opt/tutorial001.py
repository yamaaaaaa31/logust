import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, level="INFO", format="{level:<5} | {message}")


def count_rows():
    print("  counting rows... (slow)")
    return 1_000_000


logger.debug("Rows: {}", count_rows())
logger.opt(lazy=True).debug("Rows: {}", count_rows)
logger.opt(lazy=True).info("Rows: {}", count_rows)
