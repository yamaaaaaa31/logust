from logust import LogLevel, logger

logger.set_level(LogLevel.Warning)

logger.info("Server starting")
logger.warning("Cache is almost full")
