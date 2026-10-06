import logging

from logust import logger
from logust.contrib import intercept_logging

logger.add("app.json", serialize=True)

intercept_logging(target=logger.bind(source="stdlib"))

logging.getLogger("myapp").info("Tagged so you can tell it apart")
logger.info("Logged with logust directly")
