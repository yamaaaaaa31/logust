from logust import logger

logger.log("INFO", "Logged with a level name")
logger.log("warning", "Level names are case-insensitive")
logger.log(40, "Logged with a level number")
