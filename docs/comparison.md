# Comparison

## At a glance

### Logust

- Rust core and high throughput
- Loguru-style API
- Rotation, retention, JSON, async writes

### Loguru

- Rich sink options
- Long-established ecosystem

### logging

- Standard library
- Very configurable but verbose
- Slower by default

## Benchmarks (10,000 messages)

Results below are from one recent release-build run of the included benchmark suite (`benchmarks/bench_throughput.py`) on the current maintainer machine. Use `benchmarks/README.md` to reproduce them in your environment.

### Summary

Logust stayed in the mid-teens millisecond range for sync file writes, formatted messages, JSON serialization, bound context, and async file writes in this run.

### Throughput

| Scenario | logging | loguru | logust |
|----------|---------|--------|--------|
| File write (sync) | 963.57 ms | 2676.74 ms | **15.93 ms** |
| Formatted messages | 966.38 ms | 2710.67 ms | **15.65 ms** |
| JSON serialize | N/A | 2717.99 ms | **14.91 ms** |
| With context (sync) | N/A | 2600.08 ms | **14.29 ms** |

### Async writes

| Scenario | loguru | logust |
|----------|--------|--------|
| File write (async + complete) | 3019.49 ms | **16.50 ms** |
| With context (async + complete) | 3062.94 ms | **16.99 ms** |
| Async non-blocking (no wait) | 3158.39 ms | **16.18 ms** |

### Sync vs Async latency

This measures main thread time only - the true benefit of async is not blocking I/O.

| Library | Sync | Async |
|---------|------|-------|
| loguru | 2704.37 ms | 3225.03 ms |
| logust | 15.01 ms | 17.20 ms |

In this run, `loguru`'s `enqueue=True` path remained far slower than its sync path, while `logust`'s async path stayed close to its sync latency.

## Feature comparison

| Feature | logust | loguru |
|---------|--------|--------|
| Colored output | Yes | Yes |
| File rotation | Yes | Yes |
| File retention | Yes | Yes |
| Compression | Yes (gz, bz2, zip, tar, tar.gz, tar.bz2) | Yes (also xz, lzma, tar.xz, custom function) |
| File `mode` / `delay` | Yes | Yes |
| File `encoding` | UTF-8 only | Any |
| Sink error `catch` | Yes (default: silent) | Yes (default: report to stderr) |
| JSON output | Yes | Yes |
| Context binding | Yes | Yes |
| Custom levels | Yes | Yes |
| Exception catching | Yes | Yes |
| Handler `backtrace` / `diagnose` | Yes (default: off) | Yes (default: on) |
| Lazy evaluation | Yes | Yes |
| Message arguments (`"{}"`, `"{name}"`) | Yes | Yes |
| Async writes | Yes | Yes |
| Callable sinks | Yes | Yes |
| Stack info (module, function, line) | Yes | Yes |
| Process/thread info | Yes | Yes |
| Format fields (`{time:<spec>}`, `{level.icon}`, `{file.path}`, `{exception}`, ...) | Yes | Yes |
| Per-module `enable(name)` / `disable(name)` | Yes | Yes |
| loguru-shaped records in filters and patchers (`record["level"].no`, `record["time"]`, ...) | Yes | Yes |

## API differences

Most loguru code works with logust with minimal changes:

```python
# loguru
from loguru import logger
logger.add("app.log", rotation="500 MB")
logger.info("Hello")

# logust (same API for common usage)
from logust import logger
logger.add("app.log", rotation="500 MB")
logger.info("Hello")
```

### Keyword arguments and `extra`

`logger.info("{} by {user}", "login", user="alice")` formats the same in both libraries. loguru also copies every keyword argument into `extra`; logust only adds the ones not used by a placeholder, so `user` above is not in `extra`. Use `bind()` when a value should be both in the message and in `extra`. `opt(capture=False)` keeps every keyword argument out of `extra` in both libraries.

### `contextualize()`

Context-local in both libraries (a `contextvars` variable), with the same precedence:
`contextualize()` values, then `bind()` values, then the message's keyword arguments (see
[Context](guide/context.md#precedence)). Differences:

- logust's `contextualize()` yields the logger (`with logger.contextualize(...) as log:`);
  loguru's yields `None`.
- `configure(extra=...)` binds the values to the logger in logust, so they override
  `contextualize()` values like `bind()` does; in loguru they are the core defaults and
  `contextualize()` overrides them.
- A block entered in one `contextvars` context and exited in another (for example an async
  generator closed by another task) restores the previous values instead of raising
  `ValueError`.

### Callable sinks receive no trailing newline

loguru passes callable sinks the formatted message **with** a trailing `"\n"`, so its recipes use `end=""`. Logust passes it **without** one, so drop `end=""` when porting:

```python
# loguru
logger.add(lambda msg: tqdm.write(msg, end=""))
logger.add(lambda msg: print(msg, end=""))

# logust
logger.add(lambda msg: tqdm.write(msg))
logger.add(lambda msg: print(msg))
```

Keeping `end=""` with logust joins every log line into one. Stream sinks (objects with a `write()` method, such as `sys.stdout` or `io.StringIO`) get a trailing newline in both libraries.

### Format strings

loguru format strings work as is, including `{time:YYYY-MM-DD}`, `{level.icon}`, `{thread.name}`,
and `{file.path}` (see [Formatting](guide/formatting.md#format-tokens)). Differences:

- `{exception}` places the traceback once. loguru appends `"\n{exception}"` to every string
  format, so a loguru format containing `{exception}` prints it twice.
- Plain `{time}` gives `2025-12-24 12:00:00.123` (loguru: ISO 8601); use `{time:}` for ISO 8601.
- `{thread}` / `{process}` give `name:id` (loguru: the id); use `{thread.id}` / `{process.id}`.
- The `zz` time token gives the UTC offset instead of a time zone abbreviation, except with `!UTC`.
- `{extra}` sorts the keys (loguru keeps binding order) and writes values other than `str`,
  numbers, `bool`, `None`, lists, tuples and dicts with `str()` instead of `repr()`.

### Exceptions

- **`backtrace` / `diagnose`**: `add()` accepts both, as in loguru, but both default to `False`.
  loguru defaults to `True`, which writes variable values (possibly secrets) into the logs.
  Pass them explicitly for loguru's output detail.
- **Traceback style**: `diagnose=True` lists the variables used on each line as `| name = value`
  instead of loguru's annotated source lines, and `backtrace=True` adds the outer frames without
  loguru's `⥤` marker. Tracebacks are not colorized.
- `opt(backtrace=True)` / `opt(diagnose=True)` are logust additions: they turn the detail on
  for one message on every handler.

### Message markup and `opt()`

- **`opt(colors=...)`**: loguru parses color markup in a message only with `opt(colors=True)`.
  logust always parses it (stripping it on sinks without `colorize`), so `colors=True` changes
  nothing and `colors=False` keeps the tags as plain text for that message.
- **`opt(capture=False)`** works as in loguru. `opt(raw=True)` and `opt(record=True)` are not
  supported yet.

### Record dicts in filters, patchers, and callbacks

Filters, patchers, and `add_callback()` callbacks get loguru's record keys: `record["level"].no`,
`record["time"]` (an aware `datetime`), `record["elapsed"]` (a `timedelta`),
`record["file"].path`, `record["thread"].id`, `record["process"].name`, `record["module"]`
(see [The record dict](guide/context.md#the-record-dict)). Differences:

- `record["exception"]` is the traceback text or `None`, not a `(type, value, traceback)` tuple.
- `record["level"]` and `record["file"]` are also strings (`record["level"] == "INFO"` is true),
  and the record keeps logust's flat keys (`level_no`, `timestamp`, `thread_id`, ...).
- A patcher's record has no caller fields (`name`, `module`, `function`, `line`, `file`), and only
  its changes to `message`, `extra` and `exception` are used.

### File sink options

`compression`, `mode`, `encoding`, `delay` and `catch` use loguru's names, with these differences:

- **`compression`**: `"gz"`, `"bz2"`, `"zip"`, `"tar"`, `"tar.gz"` and `"tar.bz2"` are supported, and `True` still means gzip. `"xz"`, `"lzma"` and `"tar.xz"` raise `ValueError`. A compression function raises `TypeError`.
- **`mode`**: only `"a"` and `"w"` are supported.
- **`encoding`**: files are always written as UTF-8. UTF-8 aliases are accepted, and other encodings raise `ValueError`.
- **`catch`**: loguru defaults to `catch=True`, which prints sink errors to stderr. Logust defaults to `catch=None`, which drops them silently as earlier releases did. Pass `catch=True` for loguru's behavior, or `catch=False` to raise the error from the logging call.
- **Rotated file names** keep Logust's `app.<timestamp>.pid<pid>.log` pattern, with the archive extension appended (for example `.log.zip`).
- `buffering` and other `open()` arguments are not supported.

### Other differences

- **`catch()`**: Same call shapes as loguru (`@logger.catch`, `@logger.catch(...)`, `with logger.catch():`) and the same `exception`, `level`, `reraise`, `onerror`, `exclude`, and `default` options. The record message is `"An error occurred: <exception>"` (set the prefix with `message=`), not loguru's `"An error has been caught in function ..."`.
- **`level()`**: Returns `Level(name, no, color, icon)` like loguru, but `color` is a color name (`"green"`) rather than markup (`"<green><bold>"`). Level names are case-insensitive, and passing `no` for an existing level re-registers it instead of raising.
- **Time-based `rotation`**: `timedelta(days=1)`, `timedelta(hours=1)`, and `time(0, 0)` are supported and rotate on clock boundaries (midnight, top of the hour). Other intervals and times raise `ValueError`.
- **Coroutine sinks**: `async def` sinks are not supported yet; `add()` raises `TypeError` instead of silently never awaiting them.
- **`enable()` / `disable()`**: `enable("mylib")` and `disable("mylib")` follow loguru (prefix match on the dotted module name, most specific rule wins, `""` means all modules). Without a name, or with a built-in level name such as `enable("INFO")`, they keep logust's meaning of turning the console handler on and off; loguru has no such form and uses `None` for modules without `__name__`. Records from `InterceptHandler` are matched against the stdlib logger name.
- **`logger.parse()`**: Same as `logust.parse()`. It takes a file path (not an open file) and `cast` must be a dict.

## When to choose logust

- Performance and throughput are critical
- You want a loguru-style API with fewer dependencies
- You need rotation, retention, JSON, callable sinks, and async writes

## When to choose loguru

- You need full loguru compatibility for advanced features
- You need loguru's exception records or richer sink options

## Logust vs standard logging

### Advantages of logust

1. Zero configuration with readable defaults
2. Better performance out of the box
3. Simpler API with fewer moving parts
4. Built-in rotation, retention, and colors

### Migration example

```python
# Standard logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
logger.info("Hello")

# Logust (simpler)
from logust import logger
logger.add("app.log")
logger.info("Hello")
```
