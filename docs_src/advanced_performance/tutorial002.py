import sys

from logust import CollectOptions, logger

logger.remove()
logger.add(
    sys.stdout,
    format="{name}:{function}:{line} | {thread.name} | {message}",
    collect=CollectOptions(caller=False, thread=False),
)


def handle_request():
    logger.info("Request handled")


handle_request()
