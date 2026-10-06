import sys
from datetime import date

from logust import logger

logger.remove()
logger.add(sys.stderr, serialize=True)

user_logger = logger.bind(user_id=123, roles=["admin", "billing"])
user_logger.info("User action")

logger.info("Invoice sent", invoice_id="INV-7", amount=9.99, due=date(2026, 11, 1))
