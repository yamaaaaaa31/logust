from logust import logger

config = {}

with logger.catch(message="Could not read the port"):
    port = int(config["port"])

logger.info("The program goes on")
