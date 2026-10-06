import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{time:YYYY-MM-DD HH:mm:ss.SSS ZZ} | {message}")
logger.add(sys.stderr, format="{time:HH:mm:ss!UTC} UTC | {message}")
logger.add(sys.stderr, format="{time:dddd D MMMM YYYY, h:mm A} | {message}")
logger.add(sys.stderr, format="{time:%d/%m/%Y %H:%M} | {message}")

logger.info("Same moment, four formats")
