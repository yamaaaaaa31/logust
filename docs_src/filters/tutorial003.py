import sys

from chatty_sdk import fetch_rates

from logust import logger

min_levels = {
    "chatty_sdk": 30,  # WARNING and above
}


def by_module(record):
    return record["level"].no >= min_levels.get(record["name"], 0)


logger.remove()
logger.add(sys.stderr, level="DEBUG", format="{level:<8} | {name} | {message}", filter=by_module)

logger.debug("Fetching exchange rates")
rates = fetch_rates()
logger.info("Got {} rates", len(rates))
