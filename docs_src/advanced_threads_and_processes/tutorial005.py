import asyncio
import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{message} | {extra}")


async def send_email():
    await asyncio.sleep(0.01)
    logger.info("Email sent")


async def main():
    with logger.contextualize(order_id=1234):
        task = asyncio.create_task(send_email())
        logger.info("Order saved")
    logger.info("Back in main()")
    await task


asyncio.run(main())
