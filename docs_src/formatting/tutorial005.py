import sys
import threading
import time

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{elapsed} | {process.name} | {thread.name} | {message}")


def download():
    logger.info("Downloading in the background")
    time.sleep(0.2)


logger.info("Starting")
worker = threading.Thread(target=download, name="downloader")
worker.start()
worker.join()
logger.info("Done")
