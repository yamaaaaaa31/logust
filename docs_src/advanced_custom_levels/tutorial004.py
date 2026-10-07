import sys

from logust import logger

logger.remove()
logger.level("NOTICE", no=23, color="cyan")

logger.add(sys.stdout, level="NOTICE", format="{level:<8} | {message}")

logger.info("Deploying version 2.4.0")
logger.log("NOTICE", "Feature flag 'new-checkout' is now on")
logger.log(23, "The same level, by number")
logger.warning("The cache is cold")
