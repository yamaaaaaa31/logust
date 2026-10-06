from logust import logger

logger.level("NOTICE", no=23, color="cyan", icon="🔔")

print(logger.level("NOTICE"))
print(logger.level("notice").no)

logger.level("NOTICE", icon="📣")
logger.level("INFO", color="blue")

print(logger.level("NOTICE"))
print(logger.level("INFO"))
