from logust import logger

logger.remove()
logger.add("history.log")
logger.add("last-run.log", mode="w")

logger.info("Server starting")
