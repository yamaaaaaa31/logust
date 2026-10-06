import json
import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{time:HH:mm:ss} | {level:<8} | {message}")
logger.add("app.json", serialize=True, mode="w")

logger.bind(order_id=1234).info("Order created")
logger.bind(order_id=1234).warning("Payment retried")

logger.complete()
with open("app.json") as file:
    for line in file:
        record = json.loads(line)
        print(record["level"], record["extra"]["order_id"], record["message"])
