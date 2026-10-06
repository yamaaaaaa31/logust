import threading

from logust import logger

logger.remove()
logger.add("threads.log", format="{thread.name} | {message}", mode="w")


def worker():
    for i in range(1000):
        logger.info("Processed item {}", i)


threads = [threading.Thread(target=worker, name=f"worker-{n}") for n in range(4)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()

with open("threads.log") as f:
    lines = f.read().splitlines()
print(len(lines), "lines, for example:", lines[-1])
