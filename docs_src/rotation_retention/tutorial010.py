from logust import logger

try:
    logger.add("app.log", rotation="daily", retention="1 week")
except ValueError as exc:
    print(f"ValueError: {exc}")
