import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level:<8} | {message}")

logger.info("<green>Deployed</green> version <bold>2.1.0</bold>")
logger.opt(colors=False).info("Template: <b>{}</b>", "Hello")
