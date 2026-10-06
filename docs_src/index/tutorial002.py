from logust import logger

logger.add(
    "app.log",
    level="INFO",
    rotation="500 MB",
    retention="30 days",
    compression=True,
    serialize=True,
    enqueue=True,
)

logger.bind(user_id=42).info("User logged in")
logger.complete()
