# File Output

Send logs to files with rotation, retention, and compression.

!!! warning "Production best practice"
    Always set `rotation` and `retention` in production to prevent disk space issues.

## Basic file handler

```python
from logust import logger

handler_id = logger.add("app.log")
logger.info("This goes to app.log")
```

## Console sinks (stdout/stderr)

In addition to files, you can add handlers for stdout and stderr:

```python
import sys
from logust import logger

# Remove default console output
logger.remove()

# Add stdout with colors
logger.add(sys.stdout, colorize=True)

# Add stderr for JSON output
logger.add(sys.stderr, serialize=True)

# Both outputs simultaneously
logger.info("Goes to both stdout and stderr")
```

### Colorize option

Control ANSI color codes in console output:

```python
import sys
from logust import logger

# Auto-detect TTY (default when colorize=None)
logger.add(sys.stdout)  # Colors if terminal, plain if piped

# Force colors on
logger.add(sys.stdout, colorize=True)

# Force colors off
logger.add(sys.stdout, colorize=False)
```

### Multiple outputs with different formats

```python
import sys
from logust import logger

logger.remove()

# Human-readable console output
logger.add(sys.stdout, colorize=True, format="{level} | {message}")

# JSON to stderr for log aggregation
logger.add(sys.stderr, serialize=True)

# File for archival
logger.add("app.log", rotation="daily", retention="30 days")
```

## Common recipes

```python
from logust import logger

# Rotate by size
logger.add("app.log", rotation="500 MB")

# Rotate by time
logger.add("app.log", rotation="daily")

# Keep last N files
logger.add("app.log", retention=5)

# Compress rotated files
logger.add("app.log", rotation="daily", compression=True)
```

## Handler options

```python
# File handler options
logger.add(
    "app.log",
    level="INFO",           # Minimum log level
    format="{time} | {level} | {message}",  # Custom format
    rotation="500 MB",      # Rotation strategy
    retention="10 days",    # Retention policy
    compression=True,       # Compress rotated files
    serialize=True,         # JSON output
    filter=None,            # Filter callback
    enqueue=False,          # Sync writes (default)
)

# Console handler options
logger.add(
    sys.stdout,
    level="INFO",           # Minimum log level
    format="{time} | {level} | {message}",  # Custom format
    serialize=False,        # JSON output
    filter=None,            # Filter callback
    colorize=True,          # ANSI color codes (console only)
)
```

## Rotation

Rotate log files based on size or time:

```python
# Size-based rotation
logger.add("app.log", rotation="500 MB")
logger.add("app.log", rotation="1 GB")

# Time-based rotation
logger.add("app.log", rotation="daily")
logger.add("app.log", rotation="hourly")
```

### Rotation options

| Value | Description |
|-------|-------------|
| `"500 MB"` | Rotate when file reaches 500 MB |
| `"1 GB"` | Rotate when file reaches 1 GB |
| `"daily"` | Rotate daily at midnight |
| `"hourly"` | Rotate every hour |

## Retention

Automatically delete old log files:

```python
# Time-based retention
logger.add("app.log", retention="10 days")
logger.add("app.log", retention="7 days")

# Count-based retention
logger.add("app.log", retention=5)  # Keep last 5 files
```

## Compression

Compress rotated files with gzip:

```python
logger.add("app.log", rotation="daily", compression=True)
# Creates: app.2024-12-24.log.gz
```

## JSON serialization

Output logs as JSON for log aggregation systems:

```python
logger.add("app.json", serialize=True)
logger.info("Structured log")
```

Output:
```json
{"time":"2025-12-24T12:00:00.123","level":"INFO","message":"Structured log"}
```

## Async vs sync writes

```python
# Synchronous writes (default, reliable)
logger.add("app.log", enqueue=False)

# Asynchronous writes (higher throughput)
logger.add("app.log", enqueue=True)
```

!!! tip "When to use async"
    Use `enqueue=True` for high-throughput logging where some message loss is acceptable.
    Use `enqueue=False` (default) for reliable logging.

## Handler management

```python
handler_id = logger.add("app.log")

logger.remove(handler_id)  # Remove specific handler
logger.remove()            # Remove all handlers
logger.complete()          # Flush pending writes
```

## Multiple handlers

```python
from logust import logger

logger.add("app.log")
logger.add("error.log", level="ERROR")
logger.add("app.json", serialize=True)
```
