from logust import logger

logger.remove()
logger.add("logs/app.log", rotation="1 KB", retention=3)

for i in range(100):
    logger.info("Processing item {}", i)
