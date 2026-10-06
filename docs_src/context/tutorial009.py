import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level} | {message} | {extra}")

db_logger = logger.bind(component="db")

with logger.contextualize(request_id="r-17"):
    db_logger.info("Query sent")
    retry_logger = logger.bind(attempt=2)
    retry_logger.info("Retrying")

retry_logger.info("Retry finished")
