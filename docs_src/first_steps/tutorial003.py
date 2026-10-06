from logust import logger


def connect(host: str) -> None:
    logger.debug("Connecting...")
    logger.success("Connected")


connect("db.local")
logger.info("Ready")
