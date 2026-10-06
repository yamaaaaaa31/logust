from logust import logger

logger.remove()
logger.add_callback(lambda record: print(repr(record["extra"])))

logger.bind(order_id=1234, total=9.99, tags=["new"]).info("Order placed")
