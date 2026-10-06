from logust import logger

logger.add("app.log", rotation="500 MB")
logger.info("Hello")
