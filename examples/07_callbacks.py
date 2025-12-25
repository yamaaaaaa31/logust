#!/usr/bin/env python3
"""Callbacks example - React to log events programmatically.

This example demonstrates how to use callbacks to process log records,
useful for sending logs to external services, metrics collection, or alerting.
"""

from collections import Counter
from typing import Any

from logust import logger

# Collect log statistics
log_stats: Counter[str] = Counter()


def stats_callback(record: dict[str, Any]) -> None:
    """Callback that collects log level statistics."""
    level = record.get("level", "UNKNOWN")
    log_stats[level] += 1


def alert_callback(record: dict[str, Any]) -> None:
    """Callback that simulates alerting on ERROR and above."""
    level = record.get("level", "")
    if level in ("ERROR", "FAIL", "CRITICAL"):
        message = record.get("message", "")
        print(f"  [ALERT] {level}: {message}")


def external_service_callback(record: dict[str, Any]) -> None:
    """Callback that simulates sending logs to an external service."""
    # In a real application, you might:
    # - Send to Sentry, Datadog, or other monitoring services
    # - Push to a message queue (Kafka, RabbitMQ)
    # - Store in a database
    level = record.get("level", "")
    message = record.get("message", "")
    extra = record.get("extra", {})
    print(f"  [External Service] {level}: {message} | extra={extra}")


def filtered_callback(record: dict[str, Any]) -> None:
    """Callback that only processes specific records."""
    message = record.get("message", "")
    if "payment" in message.lower():
        print(f"  [Payment Monitor] Detected payment-related log: {message}")


def main() -> None:
    print("=== Log Callbacks Demo ===\n")

    # Register callbacks
    stats_id = logger.add_callback(stats_callback)
    alert_id = logger.add_callback(alert_callback, level="ERROR")
    external_id = logger.add_callback(external_service_callback, level="INFO")
    payment_id = logger.add_callback(filtered_callback)

    print("--- Generating various log messages ---\n")

    # Generate some logs
    logger.debug("Debug message - initializing")
    logger.info("Application started")
    logger.info("User logged in")
    logger.info("Payment processing started")
    logger.warning("High memory usage detected")
    logger.error("Database connection failed")
    logger.info("Payment completed successfully")
    logger.critical("System overload - taking action")

    print("\n--- Log Statistics ---\n")
    for level, count in sorted(log_stats.items()):
        print(f"  {level}: {count} messages")

    print("\n--- Removing callbacks ---\n")

    # Remove specific callback
    logger.remove_callback(stats_id)
    logger.remove_callback(alert_id)
    logger.remove_callback(external_id)
    logger.remove_callback(payment_id)

    # These logs won't trigger callbacks
    logger.info("This message has no callbacks")
    logger.error("This error has no alert callback")

    print("All callbacks removed. Logging continues normally.\n")

    # Demonstrate callback with context
    print("--- Callback with bound context ---\n")

    def context_aware_callback(record: dict[str, Any]) -> None:
        extra = record.get("extra", {})
        if extra:
            print(f"  [Context] {record.get('message')} | {extra}")

    cb_id = logger.add_callback(context_aware_callback, level="INFO")

    user_logger = logger.bind(user_id="u123", role="admin")
    user_logger.info("Admin action performed")

    logger.remove_callback(cb_id)


if __name__ == "__main__":
    main()
