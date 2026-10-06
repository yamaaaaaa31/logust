from logust import logger

logger.trace("Entering parse_config()")
logger.debug("Config file has 12 keys")
logger.info("Server starting")
logger.success("Database connected")
logger.warning("Cache is almost full")
logger.error("Could not send the email")
logger.fail("Health check failed")
logger.critical("Out of disk space")
