import itertools
import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="#{extra[seq]} | {level:<7} | {message}")

counter = itertools.count(1)


def add_sequence(record):
    record["extra"]["seq"] = next(counter)


log = logger.patch(add_sequence)

log.info("Starting the import")
log.info("Imported {} rows", 1200)
log.warning("Skipped {} invalid rows", 3)
