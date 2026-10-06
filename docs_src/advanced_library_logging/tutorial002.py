import sys

import mylib
import mylib.api

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{name} | {message}")

logger.enable("mylib.api")

mylib.connect()
mylib.api.fetch("invoice-7")
