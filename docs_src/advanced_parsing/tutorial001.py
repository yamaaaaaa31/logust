from logust import logger, parse

logger.remove()
logger.add("app.log", format="{time} | {level:<8} | {message}", mode="w")

logger.info("Server started")
logger.warning("Disk usage is at 91%")
logger.error("Payment failed")
logger.complete()

pattern = r"(?P<time>[\d-]+ [\d:.]+) \| (?P<level>\w+)\s+\| (?P<message>.*)"

for record in parse("app.log", pattern):
    print(record)
