import logging

from logust import logger
from logust.contrib import intercept_logging

intercept_logging()

logger.disable("urllib3")

logging.getLogger("urllib3.connectionpool").debug("Starting new HTTPS connection")
logging.getLogger("myapp").info("Your own logs still go through")
