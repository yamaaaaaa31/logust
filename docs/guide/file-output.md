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
logger.add("app.log", rotation="daily", compression=True)    # gzip
logger.add("app.log", rotation="daily", compression="zip")   # or "tar.gz", "bz2", ...

# Start a fresh file on every run
logger.add("app.log", mode="w")

# Only create the file once something is logged
logger.add("errors.log", level="ERROR", delay=True)
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
    compression=True,       # Compress rotated files (True = gzip, or "zip", "tar.gz", ...)
    serialize=True,         # JSON output
    filter=None,            # Filter callback
    enqueue=False,          # Sync writes (default)
    mode="a",               # "a" appends (default), "w" truncates
    encoding="utf-8",       # UTF-8 only (see below)
    delay=False,            # True: create the file on the first message
    catch=None,             # Sink error policy (see below)
)

# Console handler options
logger.add(
    sys.stdout,
    level="INFO",           # Minimum log level
    format="{time} | {level} | {message}",  # Custom format
    serialize=False,        # JSON output
    filter=None,            # Filter callback
    colorize=True,          # ANSI color codes (console only)
    catch=None,             # Sink error policy (see below)
)
```

`mode`, `encoding`, and `delay` only apply to file sinks. Passing them to a
stream or callable sink raises `TypeError`, as in loguru.

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
| `timedelta(days=1)` | Same as `"daily"` |
| `timedelta(hours=1)` | Same as `"hourly"` |
| `time(0, 0)` | Same as `"daily"` |

`datetime.timedelta` and `datetime.time` values are accepted for loguru
compatibility. Time-based rotation is aligned to the clock (midnight, or the
start of each hour), so a `timedelta(days=1)` file rotates at the next midnight,
not 24 hours after it was opened. Other intervals and times of day raise
`ValueError` instead of being approximated.

```python
from datetime import time, timedelta

logger.add("app.log", rotation=timedelta(hours=1))
logger.add("app.log", rotation=time(0, 0))
logger.add("app.log", rotation=timedelta(days=7))  # ValueError
```

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

Compress rotated files. `compression=True` uses gzip; a string picks the
format, using the same names as loguru:

```python
logger.add("app.log", rotation="daily", compression=True)
# Creates: app.2024-12-24_00-00-00_000000.pid1234.log.gz

logger.add("app.log", rotation="daily", compression="zip")
# Creates: app.2024-12-24_00-00-00_000000.pid1234.log.zip
```

| Value | Archive |
|-------|---------|
| `True`, `"gz"` | gzip (`.log.gz`) |
| `"bz2"` | bzip2 (`.log.bz2`) |
| `"zip"` | ZIP with one deflated entry (`.log.zip`) |
| `"tar"` | uncompressed tarball (`.log.tar`) |
| `"tar.gz"` | gzip-compressed tarball (`.log.tar.gz`) |
| `"tar.bz2"` | bzip2-compressed tarball (`.log.tar.bz2`) |

Archives hold the rotated file under its own name, so `unzip`, `tar` and
Python's `zipfile`/`tarfile` restore the original file. `"xz"`, `"lzma"` and
`"tar.xz"` raise `ValueError`, since Logust does not bundle an LZMA encoder.
Passing a function as `compression`, which loguru allows, raises `TypeError`.

Compression only runs when a file is rotated, so it does not slow down
writes. Retention finds rotated files in every supported format, so changing
`compression` between runs still cleans up older archives.

## File mode

```python
logger.add("app.log")            # mode="a" (default): append to an existing file
logger.add("app.log", mode="w")  # truncate the file when the sink opens it
```

With `mode="w"` only the first open truncates. Files reopened after rotation
or in a forked child are appended to. Other modes raise `ValueError`.

## Delayed file creation

With `delay=True`, the file (and its parent directories) is created when the
first message is written, not when `add()` is called. A sink that never
receives a message leaves nothing on disk:

```python
logger.add("errors.log", level="ERROR", delay=True)
```

The sink also starts out unopened, so `delay=True` adds no cost to each
write. Because the file is opened later, a path that cannot be opened is no
longer reported by `add()`. The error happens at the first write and follows
the `catch` setting.

## Encoding

Logust writes files from Rust, always as UTF-8. `encoding=` exists for
loguru compatibility. Any spelling of UTF-8 (`"utf-8"`, `"utf8"`, `"UTF-8"`,
...) is accepted, and any other encoding raises `ValueError`.

## Handling sink errors

`catch=` controls what happens when a sink fails, such as a callable that
raises, a stream whose `write()` raises, or a file that cannot be opened or
written:

| Value | Behavior |
|-------|----------|
| `None` (default) | The error is dropped silently, as in earlier Logust releases |
| `True` | A loguru-style report goes to stderr and logging continues |
| `False` | The error is raised from the logging call (`OSError` for file sinks) |

```python
logger.add(send_to_service, catch=True)
# --- Logging error in Logust Handler #3 ---
# Record was: {...}
# Traceback (most recent call last):
#   ...
# --- End of logging error ---
```

With `catch=False`, every other handler still receives the message, and then
the first error is raised.

!!! note "Difference from loguru"
    loguru's default is `catch=True`. Logust keeps `None` (silent) as the
    default so existing applications do not start writing reports to stderr.
    Pass `catch=True` to match loguru.

Console sinks (`sys.stdout`, `sys.stderr` and the default handler) follow the
same policy. Their usual failure is a reader that has gone away, as in
`python app.py | head -1`: Python ignores `SIGPIPE`, so every later write
fails with `EPIPE`. With the default `catch=None` the application keeps
running and the remaining console output is dropped; `catch=True` prints one
report per dropped message (nothing is printed when stderr itself is the
broken pipe); `catch=False` raises `BrokenPipeError` from the logging call.
A closed descriptor (`os.close(1)`) is still treated as a successful write.

For file sinks, a report or exception can only come from a failed open or
write in the calling thread. With `enqueue=True`, write errors happen on the
background writer thread and are printed to stderr whatever `catch` is set
to.

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

!!! note "Forked child processes"
    A process created with `fork()` never starts a writer thread: `enqueue=True`
    sinks inherited from the parent, and on macOS also sinks added in the child,
    write synchronously. On macOS, Rust's thread parking uses libdispatch, which
    crashes a forked child (SIGTRAP) once the parent has used it.

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
