from logust import logger

logger.info("Before disable()")

logger.disable()
print("Console enabled?", logger.is_enabled())
logger.info("Nobody sees this")

logger.enable(level="WARNING")
logger.info("Below WARNING, not shown")
logger.warning("Console is back")
