import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{level:<7} | {message}")


def load_config(path):
    raise FileNotFoundError(path)


try:
    load_config("settings.toml")
except FileNotFoundError:
    logger.opt(exception=True).warning("No config file, using the defaults")
