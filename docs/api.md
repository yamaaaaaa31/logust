# API Reference

Quick reference for the public API. For examples, see the Guide.

## Overview

- **Logger**: Log methods, handlers, levels, context, options, callbacks
- **LogLevel**: Enum values for severity
- **Parsing**: `parse()` and `parse_json()` helpers
- **Contrib**: standard logging interception, decorators, canonical events,
  FastAPI/Starlette middleware

## Logger

The main logging interface.

### Log methods

```python
logger.trace(message, *args, **kwargs)
logger.debug(message, *args, **kwargs)
logger.info(message, *args, **kwargs)
logger.success(message, *args, **kwargs)
logger.warning(message, *args, **kwargs)
logger.error(message, *args, **kwargs)
logger.fail(message, *args, **kwargs)
logger.critical(message, *args, **kwargs)
logger.exception(message, *args, **kwargs)  # ERROR with traceback
logger.log(level, message, *args, **kwargs)  # Any level
```

When `args` or `kwargs` are given, the message is formatted with
`message.format(*args, **kwargs)`; kwargs not used by a placeholder go to `extra`.
A message without arguments is logged as-is.

```python
logger.info("Processed {} items", 42)
logger.info("User {user} did {}", "login", user="alice", request_id="r1")
```

### Handler management

```python
# File sink
handler_id = logger.add(
    sink,                    # File path (str or Path), sys.stdout/stderr, or callable
    level=None,              # Minimum level (LogLevel or str)
    format=None,             # Format string (fields: docs/guide/formatting.md)
    rotation=None,           # "500 MB", "daily", "hourly", timedelta, time (files only)
    retention=None,          # "10 days" or count (int) (files only)
    compression=False,       # True (gzip), "gz", "bz2", "zip", "tar", "tar.gz", "tar.bz2" (files only)
    serialize=False,         # JSON output
    filter=None,             # Filter function
    enqueue=False,           # Async writes (files only)
    colorize=None,           # ANSI colors (console only, auto-detect if None)
    collect=None,            # CollectOptions for info collection control
    mode=None,               # "a" (append, default) or "w" (truncate) (files only)
    encoding=None,           # UTF-8 aliases only; files are always UTF-8 (files only)
    delay=None,              # True: create the file on the first message (files only)
    catch=None,              # Sink errors: None drops, True reports to stderr, False raises
    backtrace=False,         # Logged tracebacks also show frames above the catch point
    diagnose=False,          # Logged tracebacks also show variable values (may leak secrets)
)

# Console sink
import sys
logger.add(sys.stdout, colorize=True)   # stdout with colors
logger.add(sys.stderr, serialize=True)  # stderr with JSON

# Callable sink (function, lambda, method)
logger.add(lambda msg: print(msg))
logger.add(my_function, format="{level} | {message}")
logger.add(send_to_slack, level="ERROR", serialize=True)
# Coroutine functions (async def) are rejected with TypeError

# Format fields beyond {time}/{level}/{message}: loguru time specs, dotted
# attributes, and the exception placed in the format (not appended again)
logger.add(
    "app.log",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level.icon} {level.name:<8} | "
    "{thread.name} {file.path}:{line} - {message}\n{exception}",
)

# {extra} writes every extra field: "Login {'user': 'alice'}"
logger.add(sys.stderr, format="{message} {extra}")
# An invalid time spec raises ValueError: logger.add("x.log", format="{time:SSSSSSS}")
```

`mode`, `encoding` and `delay` raise `TypeError` for non-file sinks. Unsupported
`compression`, `mode` or `encoding` values raise `ValueError`. See
[File Output](guide/file-output.md) for details.

```python
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

### Module activation

```python
logger.disable("mylib")      # Drop messages from mylib and mylib.*
logger.enable("mylib.api")   # Most specific rule wins
logger.enable("mylib")       # Re-enable mylib (clears its submodule rules)
logger.disable("")           # Disable every module
logger.enable("")            # Remove every rule
```

A string passed to `enable()` is a level when it is a built-in level name
(case-insensitive), and a module name otherwise. `logust.enable()` and
`logust.disable()` are module-level shortcuts. See
[Enable or disable modules](guide/levels.md#enable-or-disable-modules).

### Custom levels

```python
level = logger.level(
    name,           # Level name (str)
    no=None,        # Numeric value (int); omit to look up or update a level
    color=None,     # Color name (str)
    icon=None,      # Icon symbol (str)
)  # -> Level(name, no, color, icon)

logger.level("INFO")                # Look up; ValueError if unknown
logger.level("INFO", color="blue")  # Update an existing level
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
    onerror=None,            # Called with the exception after logging
    exclude=None,            # Exception type(s) to let through unlogged
    default=None,            # Return value when an exception was caught
    message="An error occurred",
)
def function():
    pass

@logger.catch                # Without parentheses
def other():
    pass

with logger.catch():         # As a context manager
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
    colors=None,      # False: keep message markup as plain text
    capture=True,     # False: kwargs only format the message, not added to extra
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
        {"sink": "app.log", "level": "INFO", "rotation": "1 day", "compression": "zip"},
        {"sink": "run.log", "mode": "w", "delay": True},
        {"sink": "error.log", "level": "ERROR"},
        {"sink": "app.json", "serialize": True},
    ],
    levels=[
        {"name": "NOTICE", "no": 25, "color": "cyan"},
    ],
    extra={"app": "myapp"},  # Bound to all logs
    patcher=my_patcher,      # Applied to all logs
    activation=[("mylib", False)],  # enable()/disable() rules, in order
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

## Contrib

Utilities in `logust.contrib` are optional helpers built on top of the core
logger.

### Standard logging interception

```python
from logust.contrib import InterceptHandler, intercept_logging

intercept_logging()
```

### Function timing

```python
from logust.contrib import debug_fn, log_fn

@log_fn
def work():
    pass

@debug_fn
async def async_work():
    pass
```

### Canonical event helpers

```python
from logust.contrib import (
    TailSampler,
    add_event_fields,
    canonical_event,
    clear_event_fields,
    get_current_event,
    get_event_fields,
)

with canonical_event({"event": "job"}) as event:
    add_event_fields(job_id="job_123")
```

`add_event_fields(fields=None, **kwargs)` returns `True` when an event is active
and `False` outside a canonical event context.

`TailSampler` accepts:

```python
TailSampler(
    rate=1.0,                  # 0.0 to 1.0
    always_keep_errors=True,
    slow_ms=None,              # non-negative milliseconds
    keep_if=None,              # predicate(event) -> bool
)
```

### FastAPI / Starlette

Install web extras before importing the middleware:

```bash
pip install "logust[fastapi]"
# or
pip install "logust[starlette]"
```

```python
from logust.contrib.starlette import (
    RequestLoggerMiddleware,
    get_request_id,
    setup_fastapi,
)

setup_fastapi(
    app,
    canonical=True,
    sample_rate=0.05,
    slow_ms=1000,
    skip_routes=["/health"],
)
```

For the full event contract, see [Canonical Events](guide/canonical-events.md).

---

## Type definitions

### LogRecord

The record dict passed to filters, patchers, and `add_callback()` callbacks
(see [The record dict](guide/context.md#the-record-dict)).

```python
from logust import LogRecord

def my_filter(record: LogRecord) -> bool:
    return record["level"].no >= 30

# A record looks like:
{
    "level": "INFO",                 # RecordLevelStr: a str with .name, .no, .icon
    "level_no": 20,
    "message": "Hello",
    "time": datetime(2025, 12, 24, 12, 0, tzinfo=...),  # aware datetime
    "timestamp": "2025-12-24T12:00:00.000000+00:00",
    "elapsed": RecordElapsed(...),     # timedelta; str() gives "00:01:23.456"
    "name": "__main__",              # Module name
    "module": "main",                # File name without extension
    "function": "my_function",       # Function name
    "line": 42,                        # Line number
    "file": "main.py",               # RecordFile: a str with .name, .path
    "thread": RecordThread(...),       # .id, .name
    "thread_name": "MainThread",
    "thread_id": 12345,
    "process": RecordProcess(...),     # .id, .name
    "process_name": "MainProcess",
    "process_id": 1234,
    "exception": None,                 # Traceback text, or None
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

A named tuple with the same `name`, `no` and `icon` fields as loguru's level record.
`record["level"]` itself is a `RecordLevelStr`.

```python
from logust import RecordLevel

level = RecordLevel(name="INFO", no=20, icon="")
```

### RecordLevelStr, RecordFile, RecordThread, RecordProcess, RecordElapsed

The value types of a record's `level`, `file`, `thread`, `process` and `elapsed` keys.
Their attributes are read-only.

```python
from logust import RecordElapsed, RecordFile, RecordLevelStr, RecordProcess, RecordThread

level = RecordLevelStr("INFO", 20, "ℹ️")  # level == "INFO"; level.no == 20
file = RecordFile("main.py", "/app/main.py")  # file == "main.py"; file.path
thread = RecordThread(12345, "MainThread")  # thread.id, thread.name
process = RecordProcess(1234, "MainProcess")  # process.id, process.name
elapsed = RecordElapsed(seconds=83, microseconds=456000)  # str(elapsed) == "00:01:23.456"
```

### RecordException

A named tuple shaped like loguru's `record["exception"]`. Logust records hold the traceback
text instead (see [The record dict](guide/context.md#the-record-dict)).

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

# Also available as logger.parse(), like loguru
from logust import logger

for record in logger.parse("app.log", r"(?P<count>\d+)", cast={"count": int}):
    print(record["count"])
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
