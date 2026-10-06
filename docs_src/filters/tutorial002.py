import sys

from chatty_sdk import fetch_rates

from logust import logger


def not_from_sdk(record):
    return not record["name"].startswith("chatty_sdk")


logger.remove()
logger.add(sys.stderr, format="{level:<8} | {name} | {message}", filter=not_from_sdk)

logger.info("Fetching exchange rates")
rates = fetch_rates()
logger.info("Got {} rates", len(rates))
