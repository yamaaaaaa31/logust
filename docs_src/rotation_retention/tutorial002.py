from logust import logger

logger.remove()
logger.add("app.log", rotation="500 MB")
logger.add("debug.log", rotation="1.5 GB")
logger.add("trace.log", rotation="100 KB")
