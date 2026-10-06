from datetime import timedelta

from logust import logger

try:
    logger.add("app.log", rotation=timedelta(days=7))
except ValueError as exc:
    print(f"ValueError: {exc}")

try:
    logger.add("app.log", compression="xz")
except ValueError as exc:
    print(f"ValueError: {exc}")
