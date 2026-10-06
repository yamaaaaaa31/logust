import asyncio
import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level} | {message} | {extra}")


async def charge_card(amount):
    await asyncio.sleep(0.01)
    logger.info("Charging {} EUR", amount)


async def handle_order(order_id, amount):
    with logger.contextualize(order_id=order_id):
        logger.info("Checkout started")
        await charge_card(amount)
        logger.info("Checkout done")


async def main():
    await asyncio.gather(handle_order(1, 25), handle_order(2, 40))
    logger.info("All orders handled")


asyncio.run(main())
