import time

from logust.contrib import log_fn


@log_fn
def process_data(items):
    time.sleep(0.12)
    return [item * 2 for item in items]


result = process_data([1, 2, 3])
print(result)
