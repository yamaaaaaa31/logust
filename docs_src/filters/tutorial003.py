import sys

from chatty_sdk import fetch_rates

from logust import logger

logger.remove()
logger.add(
    sys.stderr,
    level="DEBUG",
    format="{level:<8} | {name} | {message}",
    filter={"": "DEBUG", "chatty_sdk": "WARNING"},
)

logger.debug("Fetching exchange rates")
rates = fetch_rates()
logger.info("Got {} rates", len(rates))
