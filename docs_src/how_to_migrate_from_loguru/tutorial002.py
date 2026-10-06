import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{message} | extra={extra}")

logger.info("{} by {user}", "login", user="alice", ip="10.0.0.7")
logger.bind(user="alice").info("{} by {user}", "login", user="alice")
