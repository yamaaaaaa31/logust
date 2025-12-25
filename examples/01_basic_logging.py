#!/usr/bin/env python3
"""Basic logging example - Getting started with Logust.

This example demonstrates the fundamental logging capabilities of Logust.
"""

import logust
from logust import logger

# Check version
print(f"Logust version: {logust.__version__}")
print()

# Module-level logging (like loguru)
logust.info("Hello from logust module!")
logust.debug("This is a debug message")

print()

# Logger instance logging
logger.trace("Trace - Most detailed level")
logger.debug("Debug - For debugging information")
logger.info("Info - General information")
logger.success("Success - Operation completed successfully")
logger.warning("Warning - Something might be wrong")
logger.error("Error - Something went wrong")
logger.fail("Fail - Operation failed")
logger.critical("Critical - System is in critical state")

print()

# Message formatting
name = "Alice"
count = 42
logger.info(f"User {name} performed {count} actions")

# Check if level is enabled (useful for expensive operations)
if logger.is_level_enabled("DEBUG"):
    logger.debug("This debug message will only be computed if DEBUG is enabled")

print()

# Set minimum log level
logger.set_level("WARNING")
logger.debug("This won't be shown")
logger.info("This won't be shown either")
logger.warning("This will be shown")
logger.error("This will also be shown")

# Reset to show all levels
logger.set_level("TRACE")
logger.info("Back to showing all levels")
