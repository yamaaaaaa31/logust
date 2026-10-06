import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{level:<7} | {message}")


def on_record(record):
    print(f"  -> callback got {record['level']} from {record['function']}()")


callback_id = logger.add_callback(on_record, level="WARNING")


def sync_inventory():
    logger.info("Syncing inventory")
    logger.warning("Supplier API is slow")


sync_inventory()

logger.remove_callback(callback_id)
logger.warning("Supplier API is still slow")
