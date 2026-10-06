from logust import logger

logger.remove()
logger.add("app.log")

logger.info("Saved to the file")
logger.complete()

with open("app.log") as f:
    print(f.read(), end="")
