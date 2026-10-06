from logust import logger


def load_cache():
    raise FileNotFoundError("cache.json")


try:
    load_cache()
except FileNotFoundError:
    logger.opt(exception=True).warning("No cache yet, starting empty")
