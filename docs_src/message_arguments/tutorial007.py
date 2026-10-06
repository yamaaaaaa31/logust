from logust import logger

try:
    logger.info("{} and {}", "only one")
except IndexError as exc:
    print(f"IndexError: {exc}")

try:
    logger.info("Hello {name}", user="alice")
except KeyError as exc:
    print(f"KeyError: {exc}")
