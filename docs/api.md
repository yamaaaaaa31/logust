# API Reference

Quick reference for the public API. For examples, see the Guide.

## Overview

- **Logger**: Log methods, handlers, levels, context, options, callbacks
- **LogLevel**: Enum values for severity
- **Parsing**: `parse()` and `parse_json()` helpers

## Logger

The main logging interface.

### Log methods

```python
logger.trace(message, **kwargs)
logger.debug(message, **kwargs)
logger.info(message, **kwargs)
logger.success(message, **kwargs)
logger.warning(message, **kwargs)
logger.error(message, **kwargs)
logger.fail(message, **kwargs)
logger.critical(message, **kwargs)
logger.exception(message, **kwargs)  # ERROR with traceback
logger.log(level, message, **kwargs)  # Any level
```

### Handler management

```python
handler_id = logger.add(
    sink,                    # File path (str or Path)
    level=None,              # Minimum level (LogLevel or str)
    format=None,             # Format string
    rotation=None,           # "500 MB", "daily", "hourly"
    retention=None,          # "10 days" or count (int)
    compression=False,       # Gzip compression
    serialize=False,         # JSON output
    filter=None,             # Filter function
    enqueue=False,           # Async writes
)

logger.remove(handler_id)    # Remove specific
logger.remove()              # Remove all
logger.complete()            # Flush pending writes
```

### Level control

```python
logger.set_level(level)      # Set minimum level
logger.get_level()           # Get current level
logger.is_level_enabled(level)  # Check if enabled

logger.enable(level=None)    # Enable console
logger.disable()             # Disable console
logger.is_enabled()          # Check if enabled
```

### Custom levels

```python
logger.level(
    name,           # Level name (str)
    no,             # Numeric value (int)
    color=None,     # Color name (str)
    icon=None,      # Icon symbol (str)
)
```

### Context

```python
new_logger = logger.bind(**kwargs)

with logger.contextualize(**kwargs):
    logger.info("With context")

# Patch modifies record dict before logging
def add_hostname(record):
    record["extra"]["hostname"] = socket.gethostname()

patched = logger.patch(add_hostname)
patched.info("Message")  # Includes hostname in extra

# Multiple patchers accumulate
logger.patch(f1).patch(f2).info("Both patchers applied")
```

### Exception handling

```python
@logger.catch(
    exception=Exception,     # Exception type(s)
    level="ERROR",           # Log level
    reraise=False,           # Re-raise after logging
    message="An error occurred",
)
def function():
    pass
```

### Options

```python
opt_logger = logger.opt(
    lazy=False,       # Lazy evaluation
    exception=False,  # Capture current exception
    depth=0,          # Stack frame offset
    backtrace=False,  # Extended traceback
    diagnose=False,   # Show variable values
)

# opt_logger supports all log methods with format arguments:
opt_logger.info("Value: {}", value)
opt_logger.debug("User {} did {}", user_id, action)
```

### Callbacks

```python
callback_id = logger.add_callback(callback, level=None)
logger.remove_callback(callback_id)
```

### Configuration

```python
handler_ids = logger.configure(
    handlers=[
        {"sink": "app.log", "level": "INFO", "rotation": "1 day"},
        {"sink": "error.log", "level": "ERROR"},
        {"sink": "app.json", "serialize": True},
    ],
    levels=[
        {"name": "NOTICE", "no": 25, "color": "cyan"},
    ],
    extra={"app": "myapp"},  # Bound to all logs
    patcher=my_patcher,      # Applied to all logs
)
```

---

## LogLevel

Enum for log levels.

```python
from logust import LogLevel

LogLevel.Trace      # 5
LogLevel.Debug      # 10
LogLevel.Info       # 20
LogLevel.Success    # 25
LogLevel.Warning    # 30
LogLevel.Error      # 40
LogLevel.Fail       # 45
LogLevel.Critical   # 50
```

---

## Type definitions

### LogRecord

```python
from logust import LogRecord

record: LogRecord = {
    "level": "INFO",
    "level_no": 20,
    "message": "Hello",
    "timestamp": "2025-12-24T12:00:00",
    "exception": None,
    "extra": {"user_id": "123"},
}
```

### RecordLevel

```python
from logust import RecordLevel

level = RecordLevel(name="INFO", no=20, icon="")
```

### RecordException

```python
from logust import RecordException

exc = RecordException(
    type=ValueError,
    value=ValueError("error"),
    traceback="...",
)
```

---

## Parsing

### parse()

Parse log files with regex patterns:

```python
from logust import parse

for record in parse("app.log", r"(?P<level>\w+) \| (?P<message>.*)"):
    print(record["level"], record["message"])
```

### parse_json()

Parse JSON log files:

```python
from logust import parse_json

for record in parse_json("app.json"):
    print(record["level"], record["message"])
```
