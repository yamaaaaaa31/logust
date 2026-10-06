from logust import logger

logger.info("Hello, Logust!")
logger.success("Connected to the database")
logger.warning("Disk usage is at {}%", 91)
logger.bind(user_id=42).error("Payment failed")
