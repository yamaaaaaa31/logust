import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, serialize=True)


def handle_login():
    logger.info("User logged in")


handle_login()
logger.warning("Password expires in {} days", 3)
