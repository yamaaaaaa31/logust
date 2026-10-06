from logust import logger


def is_audit(record):
    return "audit" in record["extra"]


logger.add("audit.log", format="{time} | {message} | user={extra[user]}", filter=is_audit)

logger.info("Cache warmed up")
logger.bind(audit=True, user="alice").info("Changed the billing address")
logger.bind(audit=True, user="bob").warning("Deleted an invoice")
