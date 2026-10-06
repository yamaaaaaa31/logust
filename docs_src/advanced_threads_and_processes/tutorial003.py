import sys
import sysconfig
import threading

from logust import logger

free_threaded = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))
gil_enabled = getattr(sys, "_is_gil_enabled", lambda: True)()
version = sys.version.split()[0]
print(f"Python {version}, free-threaded build: {free_threaded}, GIL enabled: {gil_enabled}")

logger.remove()
logger.add("free-threaded.log", format="{thread.name} | {message}", mode="w")


def worker():
    for i in range(2000):
        logger.info("Processed item {}", i)


threads = [threading.Thread(target=worker) for _ in range(8)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()

with open("free-threaded.log") as f:
    print(sum(1 for _ in f), "lines")
