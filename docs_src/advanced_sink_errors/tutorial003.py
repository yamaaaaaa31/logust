import sys

from logust import logger


def send_to_service(message):
    raise ConnectionError("log service unavailable")


logger.remove()
logger.add(sys.stdout, format="{level} | {message}")
logger.add(send_to_service, catch=False)

try:
    logger.info("Order {} shipped", 42)
except ConnectionError as exc:
    print(f"The logging call raised: {exc!r}")
