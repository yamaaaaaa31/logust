#!/usr/bin/env python3
"""Custom log levels example - Define your own log levels.

This example demonstrates how to create and use custom log levels.
"""

from logust import logger

# Register custom log levels
# Level numbers determine priority (higher = more severe)
# Built-in: TRACE=5, DEBUG=10, INFO=20, SUCCESS=25, WARNING=30, ERROR=40, FAIL=45, CRITICAL=50

# Create a NOTICE level between INFO and WARNING
logger.level("NOTICE", no=27, color="cyan", icon="!")

# Create a SECURITY level for security-related events
logger.level("SECURITY", no=35, color="magenta", icon="*")

# Create an AUDIT level for audit trails
logger.level("AUDIT", no=22, color="blue", icon="#")

# Create a METRIC level for metrics/telemetry
logger.level("METRIC", no=15, color="white", icon="~")


def log_with_custom_levels() -> None:
    """Demonstrate logging with custom levels."""
    # Use custom levels with logger.log()
    logger.log("NOTICE", "This is a notice - more important than info")
    logger.log("SECURITY", "User authentication attempt detected")
    logger.log("AUDIT", "Configuration changed by admin")
    logger.log("METRIC", "Response time: 45ms")


def security_example() -> None:
    """Simulate security-related logging."""
    user_id = "user_123"
    ip_address = "192.168.1.100"

    security_logger = logger.bind(user_id=user_id, ip=ip_address)

    security_logger.log("SECURITY", "Login attempt")
    security_logger.log("AUDIT", "Password changed")
    security_logger.log("SECURITY", "Session created")


def mixed_levels_example() -> None:
    """Mix built-in and custom levels."""
    logger.debug("Debug message")
    logger.log("METRIC", "CPU usage: 45%")
    logger.info("Starting process")
    logger.log("AUDIT", "Process initiated by system")
    logger.log("NOTICE", "Approaching resource limit")
    logger.warning("Resource usage high")
    logger.log("SECURITY", "Rate limit exceeded")
    logger.error("Process failed")


def level_filtering_example() -> None:
    """Show how level filtering works with custom levels."""
    print("\n--- All levels (TRACE and above) ---")
    logger.set_level("TRACE")
    logger.log("METRIC", "Metric at level 15")
    logger.log("AUDIT", "Audit at level 22")
    logger.log("NOTICE", "Notice at level 27")
    logger.log("SECURITY", "Security at level 35")

    print("\n--- Only NOTICE and above (27+) ---")
    logger.set_level("NOTICE")
    logger.log("METRIC", "This won't show (15 < 27)")
    logger.log("AUDIT", "This won't show (22 < 27)")
    logger.log("NOTICE", "This will show (27 >= 27)")
    logger.log("SECURITY", "This will show (35 >= 27)")

    # Reset
    logger.set_level("TRACE")


def log_by_number() -> None:
    """Log using numeric level directly."""
    # You can also use numeric levels directly
    logger.log(27, "Logging at level 27 (NOTICE)")
    logger.log(35, "Logging at level 35 (SECURITY)")

    # Or any arbitrary number
    logger.log(18, "Logging at level 18 (between METRIC and INFO)")


def main() -> None:
    print("=== Custom Log Levels Demo ===\n")

    print("--- Basic custom level usage ---")
    log_with_custom_levels()

    print("\n--- Security-focused logging ---")
    security_example()

    print("\n--- Mixed built-in and custom levels ---")
    mixed_levels_example()

    print("\n--- Level filtering with custom levels ---")
    level_filtering_example()

    print("\n--- Logging by numeric level ---")
    log_by_number()


if __name__ == "__main__":
    main()
