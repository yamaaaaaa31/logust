import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{level.icon} {level.name:<8} ({level.no}) | {message}")

logger.level("NOTICE", no=23, color="cyan", icon="🔔")

logger.info("Deploying version 2.4.0")
logger.log("NOTICE", "Feature flag 'new-checkout' is now on")
logger.success("Deployed")
