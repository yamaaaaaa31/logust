from logust import logger

logger.disable("mylib")


def connect():
    logger.info("Connecting to the service")
