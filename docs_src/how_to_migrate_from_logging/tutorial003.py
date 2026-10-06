import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

user = "alice"
logger.info("User %s logged in from %s", user, "10.0.0.7")
logger.info("Payment received", extra={"order_id": 1234})

try:
    result = 1 / 0
except ZeroDivisionError:
    logger.exception("Calculation failed")
