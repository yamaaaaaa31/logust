from logust import logger

logger.info("User {user} logged in from {ip}", user="alice", ip="10.0.0.1")
logger.info("{} by {user}", "login", user="alice")
