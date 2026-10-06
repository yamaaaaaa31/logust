import sys

from logust import CallerInfo, CollectOptions, ProcessInfo, ThreadInfo, logger

logger.remove()
logger.add(
    sys.stdout,
    format="{name}:{function} | {thread.name} | {process.name} | {message}",
    collect=CollectOptions(
        caller=CallerInfo(name="billing", function="worker", line=0, file="billing.py"),
        thread=ThreadInfo(name="billing-loop", id=1),
        process=ProcessInfo(name="billing", id=1000),
    ),
)


def handle_request():
    logger.info("Invoice sent")


handle_request()
