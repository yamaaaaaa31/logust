import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level} | {message} | {extra}")

user_logger = logger.bind(user_id=42, session="a1b2")
user_logger.info("Opened the dashboard")
user_logger.info("Changed the theme")

logger.info("Background job finished")
