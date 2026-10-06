import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level:<8} | {file}:{line} in {function}() | {message}")


def load_config():
    logger.debug("Reading settings.toml")
    logger.success("Configuration loaded")


load_config()
logger.critical("Shutting down")
