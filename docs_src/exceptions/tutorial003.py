from logust import logger


@logger.catch
def divide(a, b):
    return a / b


result = divide(1, 0)
print(f"divide() returned {result}")
