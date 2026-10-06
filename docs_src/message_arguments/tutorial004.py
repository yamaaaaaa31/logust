import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{level:<8} | {message} | {extra}")

logger.info("Order {order_id} paid", order_id=1234, amount=9.99, currency="EUR")
logger.info("Cache cleared", keys=128)
