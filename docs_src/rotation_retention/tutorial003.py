from datetime import time, timedelta

from logust import logger

logger.remove()
logger.add("daily.log", rotation="daily")
logger.add("hourly.log", rotation="hourly")

logger.add("also-daily.log", rotation=timedelta(days=1))
logger.add("also-hourly.log", rotation=timedelta(hours=1))
logger.add("midnight.log", rotation=time(0, 0))
