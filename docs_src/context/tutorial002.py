import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level} | {message} | {extra}")

request_logger = logger.bind(request_id="r-17")
request_logger.info("Request received")

user_logger = request_logger.bind(user_id=42)
user_logger.info("User authenticated")

request_logger.info("Request finished")
