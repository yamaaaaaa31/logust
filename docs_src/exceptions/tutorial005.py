from logust import logger


@logger.catch(ValueError, level="WARNING", message="Bad input", default=-1)
def parse_age(text):
    return int(text)


print(parse_age("42"))
print(parse_age("forty-two"))
