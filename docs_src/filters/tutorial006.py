import sys

from logust import logger


def only_admins(record):
    return record["extra"]["role"] == "admin"


logger.remove()
logger.add(sys.stderr, format="{level:<8} | {message}", filter=only_admins, catch=True)

logger.bind(role="admin").info("Rotated the API keys")
logger.info("Health check OK")
