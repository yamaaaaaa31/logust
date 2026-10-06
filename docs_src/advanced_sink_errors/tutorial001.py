import sys

from logust import logger


def send_to_service(message):
    raise ConnectionError("log service unavailable")


logger.remove()
logger.add(sys.stdout, format="{level} | {message}")
logger.add(send_to_service)

logger.info("Order {} shipped", 42)
