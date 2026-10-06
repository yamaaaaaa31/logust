import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level} | {message} | {extra}")

with logger.contextualize(user="from-contextualize", step="checkout"):
    logger.info("Only contextualize()")
    logger.bind(user="from-bind").info("bind() wins")
    logger.info("The keyword argument wins", user="from-kwarg")
