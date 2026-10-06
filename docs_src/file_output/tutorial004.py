from logust import logger

logger.remove()
logger.add("app.log")

logger.info("Saved to the file")

with open("app.log") as f:
    print(f.read(), end="")
