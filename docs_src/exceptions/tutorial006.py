from logust import logger


@logger.catch(reraise=True)
def charge(amount):
    raise ConnectionError("payment gateway timed out")


try:
    charge(25)
except ConnectionError:
    print("The caller can still handle it")
