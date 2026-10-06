import time

from logust import logger
from logust.contrib import log_fn

logger.level("TIMING", no=15, color="magenta", icon="⏱")


@log_fn(level="WARNING")
def slow_operation():
    time.sleep(0.2)


@log_fn(level="TIMING")
def quick_operation():
    return 42


slow_operation()
quick_operation()
