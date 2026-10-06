import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{function}:{line} | {message}")


def log_step(message):
    logger.info(message)


def log_step_from_caller(message):
    logger.opt(depth=1).info(message)


def import_users():
    log_step("Importing users")
    log_step_from_caller("Importing users")


import_users()
