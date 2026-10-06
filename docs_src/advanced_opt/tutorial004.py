import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{message} | extra={extra}")

logger.info("User {name} logged in", name="alice", ip="10.0.0.7")
logger.opt(capture=False).info("User {name} logged in", name="alice", ip="10.0.0.7")
