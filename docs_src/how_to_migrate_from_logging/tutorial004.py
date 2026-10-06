from logust import logger

user = "alice"
logger.info("User {} logged in from {}", user, "10.0.0.7")
logger.bind(order_id=1234).info("Payment received")

try:
    result = 1 / 0
except ZeroDivisionError:
    logger.exception("Calculation failed")
