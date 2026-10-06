from logust import logger

logger.set_level("WARNING")

logger.debug("Config file has 12 keys")
logger.info("Server starting")
logger.warning("Cache is almost full")
logger.error("Could not send the email")
