import contextvars
import sys
import threading

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{thread.name} | {message} | {extra}")


def work():
    logger.info("Working")


with logger.contextualize(job_id="j-42"):
    logger.info("Starting the threads")

    plain = threading.Thread(target=work, name="plain")
    plain.start()
    plain.join()

    context = contextvars.copy_context()
    copied = threading.Thread(target=context.run, args=(work,), name="copied")
    copied.start()
    copied.join()
