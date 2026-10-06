from logust import logger

logger.info("Progress: {:.1%}", 0.4567)
logger.info("Price: {price:>8.2f} EUR", price=9.5)
logger.info("Raw value: {!r}", "text")
logger.info("Total: {:,}", 1234567)
