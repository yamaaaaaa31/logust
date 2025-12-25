#!/usr/bin/env python3
"""File output example - Logging to files with rotation and retention.

This example demonstrates file handlers with various configurations.
"""

import tempfile
from pathlib import Path

from logust import logger

# Create a temporary directory for demo logs
with tempfile.TemporaryDirectory() as tmpdir:
    log_dir = Path(tmpdir)

    # Basic file output
    basic_log = log_dir / "basic.log"
    handler_id = logger.add(str(basic_log))
    logger.info("This goes to console AND file")
    logger.remove(handler_id)

    # File-only output (disable console first)
    file_only_log = log_dir / "file_only.log"
    logger.disable()  # Disable console
    handler_id = logger.add(str(file_only_log))
    logger.info("This goes to file only")
    logger.remove(handler_id)
    logger.enable()  # Re-enable console

    # With size-based rotation
    rotating_log = log_dir / "rotating.log"
    handler_id = logger.add(
        str(rotating_log),
        rotation="100 KB",  # Rotate when file reaches 100 KB
        retention=5,  # Keep last 5 files
    )
    logger.info("This log will rotate at 100 KB")
    logger.remove(handler_id)

    # With time-based rotation
    daily_log = log_dir / "daily.log"
    handler_id = logger.add(
        str(daily_log),
        rotation="daily",  # Rotate daily
        retention="7 days",  # Keep logs for 7 days
    )
    logger.info("This log rotates daily")
    logger.remove(handler_id)

    # With compression
    compressed_log = log_dir / "compressed.log"
    handler_id = logger.add(
        str(compressed_log),
        rotation="1 MB",
        compression=True,  # Compress rotated files with gzip
    )
    logger.info("Rotated files will be compressed")
    logger.remove(handler_id)

    # Error-only file
    error_log = log_dir / "errors.log"
    handler_id = logger.add(
        str(error_log),
        level="ERROR",  # Only ERROR and above
    )
    logger.debug("This won't go to error log")
    logger.info("This won't go to error log either")
    logger.error("This WILL go to error log")
    logger.critical("This will also go to error log")
    logger.remove(handler_id)

    # Async file writing (thread-safe, good for high-throughput)
    async_log = log_dir / "async.log"
    handler_id = logger.add(
        str(async_log),
        enqueue=True,  # Write asynchronously
    )
    for i in range(100):
        logger.info(f"Async log message {i}")
    logger.complete()  # Ensure all writes are flushed
    logger.remove(handler_id)

    # Print file contents to verify
    print("\n--- Contents of basic.log ---")
    print(basic_log.read_text())

    print("--- Contents of errors.log ---")
    print(error_log.read_text())

    print("File logging demo complete!")
