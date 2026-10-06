from logust import logger

logger.remove()
logger.add("app.log", enqueue=True)

for i in range(3):
    logger.info("Processed batch {}", i)

logger.complete()

with open("app.log") as f:
    print(f.read(), end="")
