from logust import logger


def connect():
    logger.info("Connecting to the database")


connect()
logger.warning("Running without a cache")
