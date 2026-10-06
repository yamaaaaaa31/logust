from logust import logger

logger.remove()
logger.add("logs/app.log")
logger.add("logs/errors.log", level="ERROR")

logger.info("Server starting")
logger.error("Could not send the email")
