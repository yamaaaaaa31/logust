from logust import logger


def average(values):
    return sum(values) / len(values)


try:
    result = average([])
except ZeroDivisionError:
    logger.exception("Could not compute the average")
