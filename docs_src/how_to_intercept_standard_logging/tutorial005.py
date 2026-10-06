import logging

from logust import logger
from logust.contrib import intercept_logging

logging.addLevelName(35, "NOTICE")
logger.level("NOTICE", no=35, color="cyan")

intercept_logging()

logging.getLogger("myapp").log(35, "Disk usage is at 91%")
