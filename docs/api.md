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
# File sink
handler_id = logger.add(
    sink,                    # File path (str or Path), sys.stdout/stderr, or callable
    level=None,              # Minimum level (LogLevel or str)
    format=None,             # Format string
    rotation=None,           # "500 MB", "daily", "hourly" (files only)
    retention=None,          # "10 days" or count (int) (files only)
    compression=False,       # Gzip compression (files only)
    serialize=False,         # JSON output
    filter=None,             # Filter function
    enqueue=False,           # Async writes (files only)
    colorize=None,           # ANSI colors (console only, auto-detect if None)
    collect=None,            # CollectOptions for info collection control
)

# Console sink
import sys
logger.add(sys.stdout, colorize=True)   # stdout with colors
logger.add(sys.stderr, serialize=True)  # stderr with JSON

# Callable sink (function, lambda, method)
logger.add(lambda msg: print(msg))
logger.add(my_function, format="{level} | {message}")
logger.add(send_to_slack, level="ERROR", serialize=True)

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
    "name": "__main__",           # Module name
    "function": "my_function",    # Function name
    "line": 42,                   # Line number
    "file": "main.py",            # Source file name
    "thread_name": "MainThread",  # Thread name
    "thread_id": 12345,           # Thread ID
    "process_name": "MainProcess", # Process name
    "process_id": 1234,           # Process ID
    "elapsed": "00:01:23.456",    # Time since logger start
    "exception": None,
    "extra": {"user_id": "123"},
}
```

### CollectOptions

Control what information is collected per handler. Useful for performance optimization.

```python
from logust import CollectOptions, CallerInfo, ThreadInfo, ProcessInfo

# Auto-detect from format (default)
logger.add("app.log", collect=CollectOptions())

# Disable caller collection for performance
logger.add("fast.log", collect=CollectOptions(caller=False))

# Use fixed values (avoid stack inspection)
logger.add("fixed.log", collect=CollectOptions(
    caller=CallerInfo(name="myapp", function="main", line=1, file="app.py"),
    thread=ThreadInfo(name="Worker", id=1),
    process=ProcessInfo(name="App", id=1000),
))

# Force collection even if format doesn't need it
logger.add("full.log", collect=CollectOptions(caller=True, thread=True, process=True))
```

Each field can be:

- `None` - Auto-detect from format string (default)
- `False` - Never collect (use empty defaults)
- `True` - Always collect dynamically
- `CallerInfo`/`ThreadInfo`/`ProcessInfo` - Use fixed values

### CallerInfo

Fixed caller information for log records.

```python
from logust import CallerInfo

caller = CallerInfo(
    name="mymodule",      # Module name
    function="handler",   # Function name
    line=42,              # Line number
    file="handler.py",    # Source file name
)
```

### ThreadInfo

Fixed thread information for log records.

```python
from logust import ThreadInfo

thread = ThreadInfo(
    name="WorkerThread",  # Thread name
    id=12345,             # Thread ID
)
```

### ProcessInfo

Fixed process information for log records.

```python
from logust import ProcessInfo

process = ProcessInfo(
    name="MainProcess",   # Process name
    id=1234,              # Process ID
)
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

---

## Performance

### Automatic optimization

Logust automatically optimizes based on your format string:

```python
# Fast: no caller info collected (~0.7 µs/log)
logger.add("fast.log", format="{time} | {level} - {message}")

# Slower: caller info collected (~1.2 µs/log)
logger.add("full.log", format="{time} | {level} | {name}:{function}:{line} - {message}")
```

The format is analyzed at handler creation time, and only required information is collected.

### Manual optimization with CollectOptions

For maximum performance, explicitly disable unused collection:

```python
from logust import CollectOptions

# Skip all extra info collection
logger.add("minimal.log",
    format="{time} | {level} - {message}",
    collect=CollectOptions(caller=False, thread=False, process=False)
)
```

### Callable sinks

Callable sinks automatically analyze their format string:

```python
# Format analyzed - caller info NOT collected
logger.add(my_func, format="{time} | {level} - {message}")

# Format analyzed - caller info IS collected
logger.add(my_func, format="{name}:{line} - {message}")
```

### Performance tips

1. **Use simple formats** - Avoid `{name}`, `{function}`, `{line}` if not needed
2. **Use `enqueue=True`** - For high-throughput file writes (no async overhead in Logust)
3. **Use `CollectOptions`** - Explicitly disable unused fields for critical paths
4. **Use fixed info** - Provide `CallerInfo`/`ThreadInfo`/`ProcessInfo` to avoid dynamic lookup
