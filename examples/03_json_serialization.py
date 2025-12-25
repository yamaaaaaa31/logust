#!/usr/bin/env python3
"""JSON serialization example - Structured logging for log aggregation.

This example demonstrates JSON output for structured logging, which is useful
for log aggregation tools like Elasticsearch, Splunk, or Datadog.
"""

import json
import tempfile
from pathlib import Path

from logust import logger

# Create a temporary directory for demo logs
with tempfile.TemporaryDirectory() as tmpdir:
    log_dir = Path(tmpdir)

    # JSON file output
    json_log = log_dir / "app.json"
    handler_id = logger.add(
        str(json_log),
        serialize=True,  # Output as JSON
    )

    # Basic messages
    logger.info("Application started")
    logger.debug("Initializing components")

    # With context (extra fields)
    user_logger = logger.bind(user_id="user_123", session="sess_abc")
    user_logger.info("User logged in")
    user_logger.warning("Unusual activity detected")

    # Nested context
    request_logger = user_logger.bind(request_id="req_456", endpoint="/api/users")
    request_logger.info("API request received")
    request_logger.success("API request completed")

    logger.error("An error occurred")

    # Flush and remove handler
    logger.complete()
    logger.remove(handler_id)

    # Display the JSON output
    print("--- JSON Log Output ---\n")
    with open(json_log) as f:
        for line in f:
            # Pretty print each JSON line
            record = json.loads(line)
            print(json.dumps(record, indent=2))
            print()

    # Parsing JSON logs back
    print("--- Parsing JSON Logs ---\n")
    from logust import parse_json

    for record in parse_json(str(json_log)):
        level = record["level"]
        message = record["message"]
        extra = record.get("extra", {})
        print(f"[{level}] {message}")
        if extra:
            print(f"  Extra: {extra}")
