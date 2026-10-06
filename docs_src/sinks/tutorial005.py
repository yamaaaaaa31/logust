from logust import logger


def notify_on_call(message: str) -> None:
    # Imagine this posts to your chat or paging service
    print(f"[on-call] {message}")


logger.add(notify_on_call, level="ERROR", format="{level}: {message}")

logger.info("Request handled")
logger.error("Payment provider is down")
