from logust import logger

logger.remove()
logger.add("app.log", rotation="daily", retention="10 days")
