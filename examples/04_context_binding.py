#!/usr/bin/env python3
"""Context binding example - Adding metadata to log records.

This example demonstrates how to attach contextual information to logs
using bind() for permanent binding and contextualize() for temporary binding.
"""

from logust import logger


def process_user_request(user_id: str, request_id: str) -> None:
    """Simulate processing a user request with context."""
    # Create a logger with user context
    user_logger = logger.bind(user_id=user_id, request_id=request_id)

    user_logger.info("Starting request processing")
    user_logger.debug("Validating input")
    user_logger.info("Request processed successfully")


def process_order(order_id: str, items: list[str]) -> None:
    """Simulate processing an order with temporary context."""
    logger.info("Order processing started")

    # Temporary context - only active within the 'with' block
    with logger.contextualize(order_id=order_id, item_count=len(items)):
        logger.info("Validating order")
        logger.debug("Checking inventory")
        logger.success("Order validated")

    # Context is automatically removed after the block
    logger.info("Order processing finished")


def nested_context_example() -> None:
    """Demonstrate nested context binding."""
    # Base logger with service context
    service_logger = logger.bind(service="payment-service", version="1.0")

    # Add request context
    request_logger = service_logger.bind(request_id="req_789")

    # Add transaction context
    tx_logger = request_logger.bind(transaction_id="tx_abc123")

    service_logger.info("Service level log")
    request_logger.info("Request level log")
    tx_logger.info("Transaction level log")


def main() -> None:
    print("=== Permanent Binding with bind() ===\n")
    process_user_request("user_123", "req_456")

    print("\n=== Temporary Binding with contextualize() ===\n")
    process_order("order_789", ["item1", "item2", "item3"])

    print("\n=== Nested Context Binding ===\n")
    nested_context_example()

    print("\n=== Multiple Context Values ===\n")
    # You can bind multiple values at once
    app_logger = logger.bind(
        app="my-app",
        environment="production",
        hostname="server-01",
    )
    app_logger.info("Application log with multiple context values")

    # Override specific values
    staging_logger = app_logger.bind(environment="staging")
    staging_logger.info("Now in staging environment")


if __name__ == "__main__":
    main()
