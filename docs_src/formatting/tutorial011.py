import sys

from logust import logger

logger.remove()
logger.add(
    sys.stderr,
    format="[{level:^9}] line {line:03d} | {extra[user]:<5} | {message:.30}",
)

logger.bind(user="ann").info("Short message")
logger.bind(user="bob").warning("A message that is much too long for its column")
logger.bind(user="zoë").error("Disk full 💾")
