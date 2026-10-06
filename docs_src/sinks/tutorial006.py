import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {level:<8} | {message}")
logger.add(sys.stderr, level="WARNING", format="{level}: {message} ({name}:{line})")

logger.debug("Not shown anywhere")
logger.info("Shown on stdout")
logger.warning("Shown on stdout and stderr")
