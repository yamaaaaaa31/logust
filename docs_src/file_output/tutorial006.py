from pathlib import Path

from logust import logger

logger.remove()
logger.add("app.log")
logger.add("errors.log", level="ERROR", delay=True)

logger.info("Everything is fine")
print("errors.log exists?", Path("errors.log").exists())

logger.error("Something broke")
print("errors.log exists?", Path("errors.log").exists())
