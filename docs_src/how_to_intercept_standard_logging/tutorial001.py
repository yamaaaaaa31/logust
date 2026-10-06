import logging

from logust.contrib import intercept_logging

intercept_logging()

logging.info("Hello from the standard library")

db_logger = logging.getLogger("myapp.db")
db_logger.warning("Slow query: %.2f s", 1.73)
