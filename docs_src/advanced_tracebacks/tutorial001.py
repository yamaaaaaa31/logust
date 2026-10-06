import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{level} | {message}")
logger.add("debug.log", format="{level} | {message}", backtrace=True, diagnose=True)


def average(values, skip):
    total = sum(values)
    return total / (len(values) - skip)


def report(values):
    try:
        return average(values, skip=3)
    except ZeroDivisionError:
        logger.exception("Could not compute the average")


report([4, 8, 15])

logger.complete()
print("--- debug.log ---")
with open("debug.log") as f:
    print(f.read(), end="")
