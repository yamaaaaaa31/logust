from logust import logger


def fetch_rates():
    logger.debug("Opening connection to rates.example.com")
    logger.debug("Received 512 bytes")
    logger.warning("Rate limit almost reached")
    return {"EUR": 1.0, "USD": 1.08}
