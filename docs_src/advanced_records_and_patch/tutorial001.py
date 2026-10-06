from logust import logger

logger.remove()


def show(record):
    for key, value in record.items():
        print(f"{key:>12}: {value!r}")


logger.add_callback(show)


def checkout():
    logger.bind(user="alice").info("Order {} placed", 42)


checkout()
