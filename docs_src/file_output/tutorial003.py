from logust import logger

logger.remove()
logger.add("app.log", format="{time:YYYY-MM-DD HH:mm:ss} {level} {message}")

logger.info("Server starting")
