import itertools
import sys

from logust import logger

API_TOKEN = "sk-live-123456"

logger.remove()
logger.add(sys.stdout, format="#{extra[seq]} | {level:<7} | {message}")

counter = itertools.count(1)


def add_sequence(record):
    record["extra"]["seq"] = next(counter)


def redact_token(record):
    record["message"] = record["message"].replace(API_TOKEN, "***")


log = logger.patch(add_sequence).patch(redact_token)

log.info("Calling the payments API with token {}", API_TOKEN)
log.info("Payment accepted")
