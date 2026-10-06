import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level} | {message} | user={extra[user_id]}")

logger.bind(user_id=42).info("Profile updated")
logger.info("Anonymous visit")
