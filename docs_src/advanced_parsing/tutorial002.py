from logust import logger

logger.remove()
logger.add("requests.log", format="{level} {extra[path]} {extra[status]} {extra[ms]}ms", mode="w")

logger.info("Request", path="/", status=200, ms=12)
logger.info("Request", path="/search", status=200, ms=840)
logger.info("Request", path="/cart", status=500, ms=33)

pattern = r"(?P<level>\w+) (?P<path>\S+) (?P<status>\d+) (?P<ms>\d+)ms"

slow = [
    record
    for record in logger.parse("requests.log", pattern, cast={"status": int, "ms": int})
    if record["ms"] > 500
]
print(slow)
