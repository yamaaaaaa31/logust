# Logust

[![CI](https://github.com/yamaaaaaa31/logust/actions/workflows/test.yml/badge.svg)](https://github.com/yamaaaaaa31/logust/actions/workflows/test.yml)
[![PyPI version](https://badge.fury.io/py/logust.svg)](https://badge.fury.io/py/logust)
[![Python Versions](https://img.shields.io/pypi/pyversions/logust.svg)](https://pypi.org/project/logust/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A fast, Rust-powered Python logging library inspired by [loguru](https://github.com/Delgan/loguru).

## Features

- **Blazing Fast** - Rust-powered core delivers up to 20x faster performance than loguru
- **Beautiful by Default** - Colored output with zero configuration needed
- **Simple API** - loguru-compatible interface for easy migration
- **File Management** - Size/time-based rotation, retention policies, gzip compression
- **JSON Support** - Built-in serialization for structured logging
- **Context Binding** - Attach metadata to log records with `bind()`
- **Exception Handling** - Automatic traceback capture with `catch()` decorator
- **Custom Levels** - Define your own log levels with colors and icons
- **Color Markup** - Inline `<red>color</red>` tags in log messages
- **Async Writing** - Optional thread-safe async file writes with `enqueue=True`
- **Zero-Config Integrations** - Built-in support for standard logging, FastAPI, and function timing

## Benchmarks

Comparison with Python logging and loguru (10,000 log messages):

| Scenario | logging | loguru | logust | vs loguru |
|----------|---------|--------|--------|-----------|
| File write (sync) | 74.91 ms | 74.56 ms | **6.58 ms** | 11.3x faster |
| Formatted messages | 60.36 ms | 74.49 ms | **7.05 ms** | 10.6x faster |
| JSON serialize | N/A | 147.31 ms | **5.33 ms** | 27.6x faster |
| Context binding | N/A | 68.80 ms | **5.74 ms** | 12.0x faster |

### Async writes

| Scenario | loguru | logust | vs loguru |
|----------|--------|--------|-----------|
| File write (async) | 332.27 ms | **5.78 ms** | 57.5x faster |
| Sync vs Async overhead | **4.5x slower** | **No overhead** | - |

loguru's `enqueue=True` adds significant overhead due to Python's Queue. Logust uses Rust's lock-free channels, maintaining speed while offloading I/O.

**Summary:** logust is **28.4x faster** than loguru and **8.8x faster** than standard logging on average.

## Installation

```bash
pip install logust
```

## Quick Start

```python
import logust

logust.info("Hello, Logust!")
logust.debug("Debug message")
logust.warning("Warning message")
logust.error("Error message")
logust.success("Success message")
```

Output:
```
2025-12-25 12:00:00.123 | INFO     | Hello, Logust!
2025-12-25 12:00:00.123 | DEBUG    | Debug message
2025-12-25 12:00:00.123 | WARNING  | Warning message
2025-12-25 12:00:00.123 | ERROR    | Error message
2025-12-25 12:00:00.123 | SUCCESS  | Success message
```

## Log Levels

8 built-in levels from lowest to highest severity:

```python
from logust import logger

logger.trace("Trace message")     # TRACE (5)
logger.debug("Debug message")     # DEBUG (10)
logger.info("Info message")       # INFO (20)
logger.success("Success message") # SUCCESS (25)
logger.warning("Warning message") # WARNING (30)
logger.error("Error message")     # ERROR (40)
logger.fail("Fail message")       # FAIL (45)
logger.critical("Critical!")      # CRITICAL (50)
```

### Level Filtering

```python
from logust import logger, LogLevel

# Only show WARNING and above
logger.set_level(LogLevel.Warning)
# Or using string
logger.set_level("warning")

# Check current level
current = logger.get_level()

# Check if level is enabled
if logger.is_level_enabled("DEBUG"):
    logger.debug("This runs only if DEBUG is enabled")
```

## File Output

```python
from logust import logger

# Basic file output
logger.add("app.log")

# With rotation and retention
logger.add("app.log", rotation="500 MB", retention="10 days")

# Time-based rotation with compression
logger.add("app.log", rotation="daily", compression=True)

# Error-only file with specific level
logger.add("error.log", level="ERROR")

# Async writes for high-throughput scenarios
logger.add("async.log", enqueue=True)
```

### Rotation Options

- Size-based: `"100 KB"`, `"500 MB"`, `"1 GB"`
- Time-based: `"hourly"`, `"daily"`

### Retention Options

- Time-based: `"7 days"`, `"30 days"`
- Count-based: `5` (keep last 5 files)

## JSON Output

```python
from logust import logger

# JSON file output
logger.add("app.json", serialize=True)
logger.info("Structured log")
# Output: {"time":"2025-12-25 12:00:00.123","level":"INFO","message":"Structured log"}

# With context binding
user_logger = logger.bind(user_id="123", session="abc")
user_logger.info("User action")
# Output: {"time":"...","level":"INFO","message":"User action","extra":{"user_id":"123","session":"abc"}}
```

## Custom Format

```python
from logust import logger

# Custom format template
logger.add("custom.log", format="[{level}] {message}")

# Available placeholders:
# {time}     - Timestamp
# {level}    - Log level name
# {level:<8} - Level with width specifier
# {message}  - Log message
# {extra[key]} - Extra context fields
```

## Context Binding

```python
from logust import logger

# Permanent binding - returns new logger
user_logger = logger.bind(user_id="123", session="abc")
user_logger.info("User logged in")

# Temporary binding with context manager
with logger.contextualize(request_id="req-456"):
    logger.info("Processing request")  # includes request_id
logger.info("Request done")  # no request_id
```

## Exception Handling

### The `catch()` Decorator

```python
from logust import logger

@logger.catch(ValueError, level="WARNING")
def risky_function():
    raise ValueError("Something went wrong")

risky_function()  # Logs the exception, doesn't re-raise

@logger.catch(reraise=True)
def critical_function():
    raise RuntimeError("Critical error")

critical_function()  # Logs and re-raises
```

### The `exception()` Method

```python
try:
    result = 1 / 0
except:
    logger.exception("Division failed")
    # Logs ERROR with full traceback automatically
```

### Using `opt(exception=True)`

```python
try:
    risky_operation()
except:
    logger.opt(exception=True).error("Operation failed")
```

## Color Markup

```python
from logust import logger

# Inline color tags in messages
logger.info("<red>Error</red> in <blue>module</blue>")
logger.warning("<bold><yellow>Warning:</yellow></bold> Check this")

# Available tags:
# Colors: red, green, yellow, blue, magenta, cyan, white, black
# Bright: bright_red, bright_green, bright_blue, etc.
# Styles: bold (b), italic (i), underline (u), dim, strike (s)
```

## Custom Levels

```python
from logust import logger

# Register a custom level
logger.level("NOTICE", no=25, color="cyan", icon="!")

# Use the custom level
logger.log("NOTICE", "Custom level message")
logger.log(25, "Using numeric level")
```

## Lazy Evaluation

Defer expensive computations until the message is actually emitted:

```python
def expensive_computation():
    # Only runs if DEBUG level is enabled
    return complex_calculation()

logger.opt(lazy=True).debug("Result: {}", expensive_computation)
```

## Enhanced Tracebacks

```python
try:
    a = 10
    b = 0
    result = a / b
except:
    # Show variable values at each frame
    logger.opt(diagnose=True).error("Calculation failed")
    # Output includes: a = 10, b = 0

    # Extended backtrace beyond catch point
    logger.opt(backtrace=True).error("Full stack trace")
```

## Callbacks

```python
from logust import logger

def my_callback(record):
    # Send to external service, metrics, etc.
    print(f"Log received: {record['level']} - {record['message']}")

# Add callback
callback_id = logger.add_callback(my_callback, level="ERROR")

logger.error("This triggers the callback")

# Remove callback
logger.remove_callback(callback_id)
```

## Handler Management

```python
from logust import logger

# Add handler and get ID
handler_id = logger.add("app.log")

# Remove specific handler
logger.remove(handler_id)

# Remove ALL handlers (including console)
logger.remove()

# Disable/enable console output
logger.disable()
logger.enable()

# Check if console is enabled
if logger.is_enabled():
    logger.info("Console is active")

# Flush all pending writes
logger.complete()
```

## Configure from Dict

```python
from logust import logger

logger.configure(
    handlers=[
        {"sink": "app.log", "level": "INFO", "rotation": "1 day"},
        {"sink": "debug.log", "level": "DEBUG"},
        {"sink": "app.json", "serialize": True},
    ],
    levels=[
        {"name": "NOTICE", "no": 25, "color": "cyan"},
    ],
    extra={"app": "myapp", "version": "1.0"},
)
```

## Log Parsing

Parse existing log files:

```python
from logust import parse, parse_json

# Parse text logs with regex pattern
for record in parse("app.log", r"(?P<time>[\d-]+ [\d:.]+) \| (?P<level>\w+) \| (?P<message>.*)"):
    print(record["level"], record["message"])

# Parse JSON logs
for record in parse_json("app.json"):
    print(record["level"], record["message"])
```

## Filter by Handler

```python
from logust import logger

# Only log errors from specific module
logger.add("errors.log", filter=lambda r: "database" in r.get("message", ""))

# Level-based filter
logger.add("warnings.log", filter=lambda r: r.get("level") == "WARNING")
```

## Integrations

Zero-config utilities in `logust.contrib`:

### Intercept Standard Logging

```python
from logust.contrib import intercept_logging

# Redirect ALL standard logging to logust
intercept_logging()

# Now third-party libraries use logust too
import logging
logging.info("This goes through logust!")
```

### Function Timing Decorators

```python
from logust.contrib import log_fn, debug_fn

@log_fn
def process_data(items):
    return [x * 2 for x in items]

process_data([1, 2, 3])
# Logs: "Called process_data with elapsed_time=0.001"

@debug_fn
async def fetch_user(user_id):
    return await db.get(user_id)
```

### FastAPI / Starlette Middleware

```python
from fastapi import FastAPI
from logust.contrib.starlette import setup_fastapi

app = FastAPI()
setup_fastapi(app, skip_routes=["/health"])

# That's it! You get:
# - Request/response logging with timing
# - Request IDs in all logs
# - Standard logging redirected to logust
```

## Complete API Reference

### Logger Methods

| Method | Description |
|--------|-------------|
| `trace/debug/info/success/warning/error/fail/critical(message)` | Log at specific level |
| `log(level, message)` | Log at any level (name or number) |
| `exception(message)` | Log ERROR with current traceback |
| `add(sink, **options)` | Add file handler |
| `remove(handler_id)` | Remove handler |
| `bind(**kwargs)` | Create logger with bound context |
| `contextualize(**kwargs)` | Temporary context (context manager) |
| `catch(exception, **options)` | Exception catching decorator |
| `opt(**options)` | Per-message options |
| `patch(patcher)` | Create logger with record patcher |
| `level(name, no, color, icon)` | Register custom level |
| `set_level(level)` | Set minimum console level |
| `get_level()` | Get current console level |
| `is_level_enabled(level)` | Check if level is enabled |
| `enable()/disable()` | Toggle console output |
| `complete()` | Flush all handlers |
| `add_callback(fn, level)` | Add log callback |
| `remove_callback(id)` | Remove callback |
| `configure(**options)` | Configure from dicts |

### Handler Options (`add()`)

| Option | Type | Description |
|--------|------|-------------|
| `level` | `str \| LogLevel` | Minimum level for handler |
| `format` | `str` | Custom format template |
| `rotation` | `str` | Rotation strategy |
| `retention` | `str \| int` | Retention policy |
| `compression` | `bool` | Gzip rotated files |
| `serialize` | `bool` | JSON output |
| `filter` | `callable` | Filter function |
| `enqueue` | `bool` | Async writes |

### Opt Options (`opt()`)

| Option | Description |
|--------|-------------|
| `lazy=True` | Defer callable evaluation |
| `exception=True` | Auto-capture traceback |
| `backtrace=True` | Extended stack trace |
| `diagnose=True` | Show variable values |
| `depth=N` | Stack frame adjustment |

## Development

```bash
# Clone the repository
git clone https://github.com/yamaaaaaa31/logust.git
cd logust

# Create virtual environment
uv venv && source .venv/bin/activate

# Install maturin and dev dependencies
uv pip install maturin pre-commit

# Development build
maturin develop

# Set up pre-commit hooks
pre-commit install
pre-commit install --hook-type pre-push

# Run tests
cargo test                # Rust tests
pytest tests/             # Python tests

# Run benchmarks
python benchmarks/bench_throughput.py

# Test installation
python -c "import logust; logust.info('It works!')"
```

### Pre-commit Hooks

This project uses pre-commit to maintain code quality. The following checks run automatically:

| Hook | Stage | Description |
|------|-------|-------------|
| `cargo fmt` | pre-commit | Rust formatting |
| `cargo clippy` | pre-commit | Rust linting |
| `cargo check` | pre-commit | Rust compilation check |
| `cargo test` | pre-push | Rust tests |
| `ruff` | pre-commit | Python linting + auto-fix |
| `ruff-format` | pre-commit | Python formatting |
| `mypy` | pre-commit | Python type checking |

Run all checks manually:

```bash
pre-commit run --all-files
```

## Requirements

- Python >= 3.10
- Rust (for development)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Start for Contributors

```bash
git clone https://github.com/yamaaaaaa31/logust.git
cd logust
uv venv && source .venv/bin/activate
uv pip install maturin pre-commit
maturin develop
pre-commit install
```

## License

This project is licensed under the **MIT License**.

The MIT License is a permissive license that allows:

- Commercial use
- Modification
- Distribution
- Private use

The only requirement is to include the license and copyright notice in copies of the software.

See [LICENSE](LICENSE) for the full text.

---

**Logust** - Fast logging for Python, powered by Rust.
