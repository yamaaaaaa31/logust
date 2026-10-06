import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level} | {message} {extra}")

logger.bind(user="alice", attempt=2).info("Login")
logger.info("Payment received", order_id=1234, amount=9.99)
logger.info("No context here")
