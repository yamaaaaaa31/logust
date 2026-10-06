import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{level} | {message}")


def average(values, skip):
    total = sum(values)
    return total / (len(values) - skip)


try:
    average([4, 8, 15], skip=3)
except ZeroDivisionError:
    logger.opt(diagnose=True).error("Could not compute the average")
