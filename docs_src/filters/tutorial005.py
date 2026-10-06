import sys

from chatty_sdk import fetch_rates

from logust import logger

logger.remove()
logger.add(sys.stderr, level="INFO", format="{level:<8} | {name} | {message}")
logger.add("sdk.log", level="DEBUG", format="{level:<8} | {message}", filter="chatty_sdk")

logger.info("Fetching exchange rates")
rates = fetch_rates()
logger.info("Got {} rates", len(rates))

logger.complete()
