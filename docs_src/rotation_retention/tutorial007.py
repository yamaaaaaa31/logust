from logust import logger

logger.add(
    "logs/app.log",
    level="INFO",
    rotation="500 MB",
    retention="30 days",
    compression=True,
)

logger.info("Ready for production")
