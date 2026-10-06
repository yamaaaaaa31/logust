import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level} | {message} | {extra}")

with logger.contextualize(user_id=42):
    logger.info("User context")

    with logger.contextualize(action="login"):
        logger.info("Both values")

    logger.info("Only user_id again")
