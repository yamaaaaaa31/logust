import sys

from logust import logger

handler_id = logger.add(sys.stderr, format="stderr | {level} | {message}")
print(f"New handler id: {handler_id}")

logger.info("Sent to both handlers")

logger.remove(handler_id)
logger.info("Sent to the default handler only")
