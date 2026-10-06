import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{level:<8} | {message}")


def send_alert(title, details):
    # In a real app: sentry_sdk.capture_message(), a Slack webhook, PagerDuty...
    print(f"  [ALERT] {title}")
    for key, value in details.items():
        print(f"          {key}: {value}")


def alert_on_errors(record):
    details = {"where": f"{record['name']}:{record['function']}:{record['line']}"}
    details.update(record["extra"])
    if record["exception"] is not None:
        details["error"] = record["exception"].strip().splitlines()[-1]
    send_alert(record["message"], details)


logger.add_callback(alert_on_errors, level="ERROR")


def charge(order_id, amount):
    log = logger.bind(order_id=order_id)
    log.info("Charging {} EUR", amount)
    try:
        raise ConnectionError("payment provider timed out")
    except ConnectionError:
        log.exception("Payment failed")


charge("ord_42", 19.99)
