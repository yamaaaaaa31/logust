from logust import logger


def count_lines(path):
    with open(path) as f:
        return sum(1 for _ in f)


logger.remove()
logger.add("app.log", enqueue=True)

logger.info("Order received")
print("Before complete():", count_lines("app.log"), "lines")

logger.complete()
print("After complete():", count_lines("app.log"), "lines")
