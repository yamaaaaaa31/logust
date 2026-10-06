from logust import logger

messages = []

logger.remove()
logger.add(messages.append, format="{level} | {message}")

logger.info("First message")
logger.warning("Second message")

print(messages)
