from logust import logger


def alert(exc):
    print(f"Alerting on-call: {exc!r}")


@logger.catch(exclude=KeyboardInterrupt, onerror=alert)
def main():
    raise RuntimeError("database is down")


main()
