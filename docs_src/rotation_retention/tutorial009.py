from logust import logger

for rotation in ["1 week", "midnight", 10]:
    try:
        logger.add("app.log", rotation=rotation)
    except (ValueError, TypeError) as exc:
        print(f"{type(exc).__name__}: {exc}")
