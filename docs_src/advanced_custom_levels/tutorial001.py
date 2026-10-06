from logust import logger

logger.level("NOTICE", no=23, color="cyan", icon="🔔")

logger.info("Deploying version 2.4.0")
logger.log("NOTICE", "Feature flag 'new-checkout' is now on")
logger.warning("The cache is cold")
