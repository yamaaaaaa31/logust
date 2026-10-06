import sys

import mylib

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{name} | {message}")

logger.info("Application starting")
mylib.connect()

logger.enable("mylib")
mylib.connect()
