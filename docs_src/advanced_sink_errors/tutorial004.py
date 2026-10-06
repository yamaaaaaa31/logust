import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{level} | {message}")

for i in range(1000):
    logger.info("Processing item {}", i)

print("Done: 1000 items processed", file=sys.stderr)
