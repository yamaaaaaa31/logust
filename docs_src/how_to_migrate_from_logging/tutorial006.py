from logust import logger

logger.add(
    "app.log",
    level="INFO",
    rotation="10 MB",
    retention=5,
)
logger.add("daily.log", rotation="daily", retention="7 days")

logger.info("Rotation without RotatingFileHandler")
logger.complete()
