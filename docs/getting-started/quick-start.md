# Quick Start

Get a logger in one line, then add configuration when you need it.

!!! tip "loguru compatible"
    Same API as loguru - easy migration from existing code.

## Choose your style

=== "Module-level"
    ```python
    import logust

    logust.info("Hello, Logust!")
    logust.debug("Debug message")
    logust.warning("Warning message")
    logust.error("Error message")
    ```

=== "Logger instance"
    ```python
    from logust import logger

    logger.info("Info message")
    logger.debug("Debug message")
    logger.success("Success message")
    ```

## Set the minimum level

```python
from logust import logger, LogLevel

logger.set_level(LogLevel.Warning)
logger.info("This will not be shown")
logger.warning("This will be shown")
```

## Add a file sink

```python
from logust import logger

logger.add("app.log")
logger.add("error.log", level="ERROR")
```

## Common recipes

!!! info "Performance tip"
    Use `enqueue=True` for async file writes in high-throughput scenarios.

```python
from logust import logger

# Rotate and retain
logger.add("app.log", rotation="500 MB", retention="10 days")

# JSON output
logger.add("app.json", serialize=True)
logger.info("Structured log")

# Bind context
user_logger = logger.bind(user_id="123")
user_logger.info("User action")

# Catch exceptions
@logger.catch()
def risky():
    return 1 / 0
```

## Next steps

- [File output](../guide/file-output.md)
- [Formatting](../guide/formatting.md)
- [Context binding](../guide/context.md)
- [Exception handling](../guide/exceptions.md)
