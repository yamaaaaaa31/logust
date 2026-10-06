import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level} | {message} | {extra}")


def charge_card(amount):
    logger.info("Charging {} EUR", amount)


def checkout(order_id):
    with logger.contextualize(order_id=order_id):
        logger.info("Checkout started")
        charge_card(25)
        logger.info("Checkout done")


checkout(1234)
logger.info("Waiting for the next order")
