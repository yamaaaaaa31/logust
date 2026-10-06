from logust import logger

logger.remove()
logger.add("logs/app.log", rotation="1 KB")

for i in range(40):
    logger.info("Processing item {}", i)
