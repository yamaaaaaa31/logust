import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{message} | {extra}")


def read_rows():
    with logger.contextualize(source="orders.csv"):
        yield "row 1"
        yield "row 2"


for row in read_rows():
    logger.info("Got {}", row)

logger.info("Done")
