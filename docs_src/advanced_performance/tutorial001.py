import time

from logust import logger

logger.remove()

FORMATS = {
    "without caller": "{time} | {level} - {message}",
    "with caller": "{time} | {level} | {name}:{function}:{line} - {message}",
}

for label, fmt in FORMATS.items():
    handler_id = logger.add("app.log", format=fmt)
    start = time.perf_counter()
    for i in range(100_000):
        logger.info("Processed item {}", i)
    elapsed = time.perf_counter() - start
    logger.remove(handler_id)
    print(f"{label:<15} {elapsed / 100_000 * 1e6:.2f} µs per message")
