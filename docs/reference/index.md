# Reference { #reference }

Here's the reference for the public API of Logust: every class, function and parameter, with its signature and defaults.

It's meant for looking things up. If you want to **learn** Logust, read the [Tutorial - User Guide](../tutorial/index.md) and the [Advanced User Guide](../advanced/index.md), which explain all of this with examples.

## Overview { #overview }

Everything below is importable from `logust`:

| Name | Kind | Section |
|------|------|---------|
| `logger` | The global `Logger` instance | [Logger](#logger) |
| `Logger` | Logger class | [Logger](#logger) |
| `OptLogger` | Returned by `logger.opt()` | [`opt()`](#opt) |
| `LogLevel` | Built-in level enum | [`LogLevel`](#loglevel) |
| `Rotation` | Rotation enum | [`Rotation`](#rotation) |
| `PyLogger` | Rust core of a `Logger` | [`PyLogger`](#pylogger) |
| `Level` | Returned by `logger.level()` | [`Level`](#level) |
| `CollectOptions`, `CallerInfo`, `ThreadInfo`, `ProcessInfo` | Per-handler collection options | [`CollectOptions`](#collectoptions) |
| `LogRecord`, `RecordLevel`, `RecordException` | Record types | [Record types](#record-types) |
| `RecordLevelStr`, `RecordFile`, `RecordThread`, `RecordProcess`, `RecordElapsed` | Record value types | [Record value types](#record-value-types) |
| `HandlerConfig`, `LevelConfig` | `configure()` dict types | [Configuration types](#configuration-types) |
| `FilterCallback`, `PatcherCallback`, `LogCallback` | Callback protocols | [Callback protocols](#callback-protocols) |
| `FilterType` | What `add(filter=...)` accepts | [Callback protocols](#callback-protocols) |
| `parse`, `parse_json` | Log file parsers | [Parsing](#parsing) |
| `__version__` | Version string, e.g. `"0.5.0"` | |

The integrations live in `logust.contrib` and `logust.contrib.starlette`: see [Contrib](#contrib).

### Module-level shortcuts { #module-level-shortcuts }

The `logust` module forwards to the global `logger`:

```python
import logust

logust.info("Hello")            # Same as logger.info("Hello")
logust.add("app.log")           # Any Logger attribute: logust.<name> is logger.<name>
logust.disable("mylib")
```

`trace`, `debug`, `info`, `success`, `warning`, `error`, `fail`, `critical`, `exception` and `log` are bound module attributes. Every other `Logger` attribute is resolved on access.

---

## Logger { #logger }

```python
from logust import logger
```

`logger` is the global `Logger`. It starts with one console handler that writes to `sys.stdout` at the `DEBUG` level. Bound loggers (from `bind()`, `patch()`, `contextualize()`) share its handlers, levels and module rules.

### Log methods { #log-methods }

```python
logger.trace(message, *args, exception=None, **kwargs)
logger.debug(message, *args, exception=None, **kwargs)
logger.info(message, *args, exception=None, **kwargs)
logger.success(message, *args, exception=None, **kwargs)
logger.warning(message, *args, exception=None, **kwargs)
logger.error(message, *args, exception=None, **kwargs)
logger.fail(message, *args, exception=None, **kwargs)
logger.critical(message, *args, exception=None, **kwargs)
logger.exception(message, *args, **kwargs)
logger.log(level, message, *args, exception=None, **kwargs)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `message` | `str` | The message. Color markup (`<red>...</red>`) is parsed. |
| `*args` | `Any` | Positional `str.format()` arguments. |
| `exception` | `str | None` | Traceback text to attach to the record. |
| `**kwargs` | `Any` | Keyword `str.format()` arguments. Those not used by a placeholder are added to `extra`. |
| `level` | `str | int` | `log()` only. A level name (case-insensitive) or number. |

* With no `args` and no `kwargs`, the message is logged as it is (braces are not interpreted).
* `exception()` logs at `ERROR` with the traceback of the exception being handled. Outside an `except` block, it logs a plain `ERROR` message.
* `log()` with a number or name that is not a registered level raises `ValueError: Invalid log level`.

```python
logger.info("Processed {} items", 42)
logger.info("User {user} did {}", "login", user="alice", request_id="r1")  # extra: request_id
logger.log("NOTICE", "Custom level")
```

See [Message Arguments](../tutorial/message-arguments.md) and [Logging Exceptions](../tutorial/exceptions.md).

### add() { #add }

```python
logger.add(
    sink,
    *,
    level=None,
    format=None,
    rotation=None,
    retention=None,
    compression=False,
    serialize=False,
    filter=None,
    enqueue=False,
    colorize=None,
    collect=None,
    mode=None,
    encoding=None,
    delay=None,
    catch=None,
    backtrace=False,
    diagnose=False,
) -> int
```

Adds a handler and returns its ID.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sink` | `str | os.PathLike | TextIO | Callable[[str], Any]` | | A file path, a stream (any object with `write()`, like `sys.stdout` or `io.StringIO`), or a callable that receives the formatted message (without a trailing newline). A stream is bound when `add()` is called. |
| `level` | `LogLevel | str | None` | `None` | Minimum level. A built-in level name or `LogLevel`. |
| `format` | `str | None` | `None` | Format string. `None` uses `"{time} | {level:<8} | {name}:{function}:{line} - {message}"`. See [Formatting](../tutorial/formatting.md). |
| `rotation` | `str | timedelta | time | None` | `None` | Files only. `"500 MB"`, `"daily"` / `"1 day"`, `"hourly"` / `"1 hour"`, `timedelta(days=1)`, `timedelta(hours=1)`, `time(0, 0)`. Boundaries are local wall-clock times. Other values raise. See [Rotation](../tutorial/rotation-retention.md). |
| `retention` | `str | int | None` | `None` | Files only. `"10 days"`, or a number of files. Other strings raise `ValueError`. See [Retention](../tutorial/rotation-retention.md#retention). |
| `compression` | `bool | str` | `False` | Files only. `True` (gzip), `"gz"`, `"bz2"`, `"zip"`, `"tar"`, `"tar.gz"`, `"tar.bz2"`. |
| `serialize` | `bool` | `False` | Write JSON lines. See [JSON Output](../tutorial/json-output.md). |
| `filter` | `FilterType` | `None` | Which records this sink takes. A string keeps a module and its submodules (`"mypkg"` matches `mypkg` and `mypkg.db`, not `mypkgx`; `""` matches all). A dict maps modules to a minimum level, the closest parent module in the dict deciding (`{"": "WARNING", "mypkg": "DEBUG", "noisy": False}`; values: level name, number, `True` for all, `False` for none). A callable receives the record dict and returns `True` to keep it; if it raises, the record is dropped and the error follows `catch`. See [Filtering Records](../tutorial/filters.md). |
| `enqueue` | `bool` | `False` | Files only. Write in a background thread. See [Async Writes](../advanced/async-writes.md). |
| `colorize` | `bool | None` | `None` | ANSI colors and markup rendering. `None`: auto-detect for streams (TTY, `NO_COLOR`, `FORCE_COLOR`, CI, PyCharm, Jupyter); `False` for files, callables and `serialize=True`. |
| `collect` | `CollectOptions | None` | `None` | What to collect for this handler. `None`: detected from `format`. See [`CollectOptions`](#collectoptions). |
| `mode` | `str | None` | `None` | Files only. `"a"` (append, default) or `"w"` (truncate on first open). |
| `encoding` | `str | None` | `None` | Files only. UTF-8 aliases only: files are always UTF-8. |
| `delay` | `bool | None` | `None` | Files only. `True`: create the file on the first message. |
| `catch` | `bool | None` | `None` | Sink errors, and errors raised by a `filter` callable. `None`: drop silently. `True`: print a report to stderr. `False`: raise from the logging call. See [Sink Errors](../advanced/sink-errors.md). |
| `backtrace` | `bool` | `False` | Logged tracebacks also show the frames above the catch point. |
| `diagnose` | `bool` | `False` | Logged tracebacks also show variable values (can leak secrets). See [Tracebacks](../advanced/tracebacks.md). |

Raises:

* `TypeError`: `mode`, `encoding` or `delay` for a non-file sink; an `async def` sink; an unknown keyword argument; a `rotation` or `retention` of another type; a `filter` that is not a string, dict or callable, or a dict with a non-string key or a value that is not a level name, number or `bool`.
* `ValueError`: an unsupported `compression`, `mode`, `encoding`, `rotation` or `retention` value (for example `rotation="1 week"`); a `filter` dict with an unknown level name or a negative number; the built-in `filter()` function as `filter`.

```python
import sys

logger.add("app.log", rotation="500 MB", retention="10 days", compression="zip")
logger.add(sys.stderr, level="WARNING", serialize=True)
logger.add(lambda msg: print(msg), format="{level} | {message}")
```

### remove() { #remove }

```python
logger.remove(handler_id: int | None = None) -> bool
```

Removes the handler with that ID, or **all** handlers (the console handler included) when `handler_id` is `None`. Returns `True` if a handler was removed. Callable sinks can also be removed with `remove_callback()`.

### complete() { #complete }

```python
logger.complete() -> None
```

Flushes all file handlers and waits for pending background writes (`enqueue=True`). See [Make sure it's written](../tutorial/file-output.md#make-sure-its-written).

### Level control { #level-control }

```python
logger.set_level(level: LogLevel | str) -> None
logger.get_level() -> LogLevel
logger.is_level_enabled(level: LogLevel | str) -> bool
logger.enable(name: str | LogLevel | None = None, *, level: LogLevel | str | None = None) -> None
logger.disable(name: str | None = None) -> None
logger.is_enabled() -> bool
```

| Method | Description |
|--------|-------------|
| `set_level(level)` | Sets the minimum level of the **console** handler. |
| `get_level()` | Returns the console handler's minimum level. |
| `is_level_enabled(level)` | `True` if at least one handler accepts that level. |
| `enable()` / `enable(level)` | Turns the console handler back on, optionally with a level. `level` can be passed positionally (a built-in level name or `LogLevel`) or as `level=`. |
| `disable()` | Turns the console handler off. |
| `is_enabled()` | `True` if the console handler is on. |

`set_level()`, `is_level_enabled()` and `level=` take built-in levels only. See [Log Levels](../tutorial/log-levels.md).

### Module activation { #module-activation }

```python
logger.disable("mylib")      # Drop messages from mylib and mylib.*
logger.enable("mylib.api")   # The most specific rule wins
logger.enable("mylib")       # Re-enable mylib (clears its submodule rules)
logger.disable("")           # Disable every module
logger.enable("")            # Remove every rule
```

A string passed to `enable()` is a **level** when it's a built-in level name (case-insensitive), and a **module name** otherwise. Names are matched against the caller's `__name__`, and against the `logging` logger name for records from [`InterceptHandler`](#interception). `disable()` with a non-`str` name raises `TypeError`. See [Logging in Libraries](../advanced/library-logging.md).

### level() { #level-method }

```python
logger.level(
    name: str,
    no: int | None = None,
    color: str | None = None,
    icon: str | None = None,
) -> Level
```

| Call | Effect |
|------|--------|
| `level(name, no=..., color=..., icon=...)` | Registers a level, or re-registers a custom one. |
| `level(name)` | Returns the [`Level`](#level) of an existing level. `ValueError` if unknown. |
| `level(name, color=..., icon=...)` | Updates an existing level, built-in levels included. |

Names are case-insensitive. Changing the `no` of a built-in level raises `TypeError`.

Built-in levels:

| Name | `no` | `color` | `icon` |
|------|------|---------|--------|
| `TRACE` | 5 | `cyan` | ✏️ |
| `DEBUG` | 10 | `blue` | 🐞 |
| `INFO` | 20 | `green` | ℹ️ |
| `SUCCESS` | 25 | `bright_green` | ✅ |
| `WARNING` | 30 | `yellow` | ⚠️ |
| `ERROR` | 40 | `red` | ❌ |
| `FAIL` | 45 | `magenta` | ✖️ |
| `CRITICAL` | 50 | `bright_red` | ☠️ |

See [Custom Levels](../advanced/custom-levels.md).

### Context { #context }

```python
logger.bind(**kwargs) -> Logger
logger.contextualize(**kwargs) -> ContextManager[Logger]
logger.patch(patcher: Callable[[dict], None]) -> Logger
```

| Method | Description |
|--------|-------------|
| `bind(**kwargs)` | Returns a new logger that adds `kwargs` to `extra` of every record. |
| `contextualize(**kwargs)` | Within the `with` block, adds `kwargs` to `extra` of every record logged by any logger. Context-local (`contextvars`): each thread and asyncio task sees only its own blocks. Yields the logger. Precedence: `contextualize()` < `bind()` < message keyword arguments. |
| `patch(patcher)` | Returns a new logger that calls `patcher(record)` before each record is sent. Patchers accumulate. |

A patcher's record has no caller fields, and only its changes to `message`, `extra` and `exception` are used. See [Adding Context](../tutorial/context.md) and [Records and patch()](../advanced/records-and-patch.md).

### catch() { #catch }

```python
logger.catch(
    exception=Exception,
    *,
    level="ERROR",
    reraise=False,
    onerror=None,
    exclude=None,
    default=None,
    message="An error occurred",
)
```

Use as a decorator (`@logger.catch`, `@logger.catch(...)`) or a context manager (`with logger.catch():`).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `exception` | `type[BaseException] | tuple[...]` | `Exception` | Exception types to catch. |
| `level` | `str | int` | `"ERROR"` | Level of the logged record. |
| `reraise` | `bool` | `False` | Re-raise after logging. |
| `onerror` | `Callable[[BaseException], Any] | None` | `None` | Called with the exception after it is logged. |
| `exclude` | `type[BaseException] | tuple[...] | None` | `None` | Exception types that propagate without being logged. |
| `default` | `Any` | `None` | Return value of the decorated function when an exception was caught. |
| `message` | `str` | `"An error occurred"` | Message prefix. The record message is `"<message>: <exception>"`. |

See [The catch() decorator](../tutorial/exceptions.md#the-catch-decorator).

### opt() { #opt }

```python
logger.opt(
    *,
    lazy=False,
    exception=False,
    depth=0,
    backtrace=False,
    diagnose=False,
    colors=None,
    capture=True,
) -> OptLogger
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `lazy` | `False` | Call callable `args` only if the message is emitted. |
| `exception` | `False` | Attach the traceback of the exception being handled. |
| `depth` | `0` | Report a caller that many frames further up the stack. |
| `backtrace` | `False` | Show the frames above the catch point, on every handler. |
| `diagnose` | `False` | Show variable values in the traceback, on every handler. |
| `colors` | `None` | `False`: keep the message markup as plain text. `None` / `True`: render it. |
| `capture` | `True` | `False`: keyword arguments only format the message; nothing goes to `extra`. |

The `OptLogger` has `trace()`, `debug()`, `info()`, `success()`, `warning()`, `error()`, `fail()`, `critical()` and `log()`, with the same arguments as the [log methods](#log-methods) (without `exception=`). It has no `exception()` method: use `opt(exception=True).error(...)`.

```python
logger.opt(lazy=True).debug("Result: {}", expensive_function)
logger.opt(exception=True).warning("Retrying")
```

See [Per-message Options with opt()](../advanced/opt.md).

### Callbacks { #callbacks }

```python
logger.add_callback(callback: Callable[[dict], None], level: LogLevel | str | None = None) -> int
logger.remove_callback(callback_id: int) -> bool
```

`add_callback()` calls `callback(record)` with the [record dict](#logrecord) of every message at or above `level`, and returns an ID for `remove_callback()`. See [Callbacks](../advanced/callbacks.md).

### configure() { #configure }

```python
logger.configure(
    *,
    handlers: list[dict] | None = None,
    levels: list[dict] | None = None,
    extra: dict | None = None,
    patcher: Callable[[dict], None] | None = None,
    activation: list[tuple[str, bool]] | None = None,
) -> list[int]
```

| Parameter | Description |
|-----------|-------------|
| `handlers` | Dicts of [`add()`](#add) arguments, with a required `sink` key. Accepted keys: `sink`, `level`, `format`, `rotation`, `retention`, `compression`, `serialize`, `filter`, `enqueue`, `colorize`, `mode`, `encoding`, `delay`, `catch`, `backtrace`, `diagnose` (see [`HandlerConfig`](#configuration-types)). `collect` is not read. |
| `levels` | Dicts of [`level()`](#level-method) arguments: `name` (required), `no`, `color`, `icon`. Applied before the handlers. |
| `extra` | Bound to every record of this logger. |
| `patcher` | Added to this logger's patchers. |
| `activation` | `(module_name, enabled)` pairs applied in order with `enable(name)` / `disable(name)`. |

Returns the IDs of the added handlers. It doesn't remove existing handlers: call `logger.remove()` first for a clean setup.

```python
logger.configure(
    handlers=[
        {"sink": "app.log", "level": "INFO", "rotation": "1 day", "compression": "zip"},
        {"sink": "app.json", "serialize": True},
    ],
    levels=[{"name": "NOTICE", "no": 25, "color": "cyan"}],
    extra={"app": "myapp"},
    activation=[("mylib", False)],
)
```

### parse() { #logger-parse }

`logger.parse` is the same function as [`logust.parse`](#parse).

---

## LogLevel { #loglevel }

```python
from logust import LogLevel
```

| Member | `.value` | `.name` |
|--------|----------|---------|
| `LogLevel.Trace` | 5 | `"TRACE"` |
| `LogLevel.Debug` | 10 | `"DEBUG"` |
| `LogLevel.Info` | 20 | `"INFO"` |
| `LogLevel.Success` | 25 | `"SUCCESS"` |
| `LogLevel.Warning` | 30 | `"WARNING"` |
| `LogLevel.Error` | 40 | `"ERROR"` |
| `LogLevel.Fail` | 45 | `"FAIL"` |
| `LogLevel.Critical` | 50 | `"CRITICAL"` |

Members support `==`, `hash()` and `int()`. To compare severities, compare `.value` (`LogLevel.Info.value < LogLevel.Error.value`). Custom levels have no `LogLevel` member.

## Rotation { #rotation }

```python
from logust import Rotation
```

`Rotation.Never`, `Rotation.Daily`, `Rotation.Hourly`. It's the rotation enum of the Rust core; `add(rotation=...)` doesn't accept it (it raises `TypeError`). Use the strings `"daily"` and `"hourly"` instead.

## PyLogger { #pylogger }

```python
PyLogger(level: LogLevel | None = None)
```

The Rust core that a `Logger` wraps. You don't use it directly, except to create an **independent** logger with its own handlers, levels and console handler:

```python
from logust import Logger, LogLevel, PyLogger

my_logger = Logger(PyLogger(LogLevel.Info))
```

## Level { #level }

```python
class Level(NamedTuple):
    name: str
    no: int
    color: str   # Color name, like "green"
    icon: str    # "" if none
```

Returned by [`logger.level()`](#level-method).

---

## CollectOptions { #collectoptions }

Controls what a handler collects for each record. By default, Logust reads the handler's format and collects only what it uses.

```python
CollectOptions(
    caller: bool | CallerInfo | None = None,
    thread: bool | ThreadInfo | None = None,
    process: bool | ProcessInfo | None = None,
)
CallerInfo(name: str = "", function: str = "", line: int = 0, file: str = "")
ThreadInfo(name: str = "", id: int = 0)
ProcessInfo(name: str = "", id: int = 0)
```

Each field can be:

* `None`: detect from the format (default).
* `False`: never collect (empty values).
* `True`: always collect.
* A `CallerInfo` / `ThreadInfo` / `ProcessInfo`: use these fixed values, without inspecting anything.

All four are frozen dataclasses.

```python
from logust import CallerInfo, CollectOptions

logger.add("fast.log", collect=CollectOptions(caller=False))
logger.add("fixed.log", collect=CollectOptions(caller=CallerInfo(name="myapp", function="main")))
logger.add("full.log", collect=CollectOptions(caller=True, thread=True, process=True))
```

See [Performance](../advanced/performance.md).

---

## Record types { #record-types }

### LogRecord { #logrecord }

A `TypedDict` describing the record dict passed to filters, patchers and `add_callback()` callbacks:

| Key | Type | Description |
|-----|------|-------------|
| `level` | `RecordLevelStr` | Level name; a `str` with `.name`, `.no`, `.icon`. |
| `level_no` | `int` | Level number. |
| `message` | `str` | The message. |
| `time` | `datetime` | Aware time of the record. |
| `timestamp` | `str` | RFC 3339 time. |
| `elapsed` | `RecordElapsed` | Time since the logger started. |
| `name` | `str` | Caller's module `__name__`. |
| `module` | `str` | Caller's file name without extension. |
| `function` | `str` | Caller's function. |
| `line` | `int` | Caller's line. |
| `file` | `RecordFile` | Caller's file name; a `str` with `.name`, `.path`. |
| `thread` | `RecordThread` | `.id`, `.name`. |
| `thread_name`, `thread_id` | `str`, `int` | Same as `thread`. |
| `process` | `RecordProcess` | `.id`, `.name`. |
| `process_name`, `process_id` | `str`, `int` | Same as `process`. |
| `exception` | `str | None` | Traceback text. |
| `extra` | `dict[str, Any]` | Context from `bind()`, `contextualize()` and unused keyword arguments. |

In these records, the values of `extra` are converted to `str`. See [The record dict](../tutorial/filters.md#the-record-dict).

```python
from logust import LogRecord

def my_filter(record: LogRecord) -> bool:
    return record["level"].no >= 30
```

### RecordLevel { #recordlevel }

```python
class RecordLevel(NamedTuple):
    name: str
    no: int
    icon: str = ""
```

The shape of loguru's level record. `record["level"]` itself is a [`RecordLevelStr`](#record-value-types).

### RecordException { #recordexception }

```python
class RecordException(NamedTuple):
    type: type[BaseException] | None
    value: BaseException | None
    traceback: str | None
```

The shape of loguru's `record["exception"]`. Logust records hold the traceback **text** instead.

### Record value types { #record-value-types }

The types of the `level`, `file`, `thread`, `process` and `elapsed` values of a record. Their attributes are read-only (`AttributeError` on assignment).

```python
from logust import RecordElapsed, RecordFile, RecordLevelStr, RecordProcess, RecordThread

RecordLevelStr("INFO", 20, "ℹ️")        # == "INFO"; .name, .no, .icon
RecordFile("main.py", "/app/main.py")  # == "main.py"; .name, .path
RecordThread(12345, "MainThread")      # .id, .name
RecordProcess(1234, "MainProcess")     # .id, .name
RecordElapsed(seconds=83, microseconds=456000)  # a timedelta; str() == "00:01:23.456"
```

---

## Configuration types { #configuration-types }

`TypedDict`s for the dicts of [`configure()`](#configure):

* `HandlerConfig`: `sink`, `level`, `format`, `rotation`, `retention`, `compression`, `serialize`, `filter`, `enqueue`, `colorize`, `mode`, `encoding`, `delay`, `catch`, `backtrace`, `diagnose`.
* `LevelConfig`: `name`, `no`, `color`, `icon`.

## Callback protocols { #callback-protocols }

`Protocol`s for type hints:

| Name | Signature | Used by |
|------|-----------|---------|
| `FilterCallback` | `(record: dict) -> bool` | `add(filter=...)` |
| `PatcherCallback` | `(record: dict) -> None` | `patch()`, `configure(patcher=...)` |
| `LogCallback` | `(record: dict) -> None` | `add_callback()` |

`FilterType` is the type of `add(filter=...)` and `HandlerConfig["filter"]`: `str | dict[str | None, str | int | bool] | Callable[[dict[str, Any]], bool] | None`.

---

## Parsing { #parsing }

### parse() { #parse }

```python
parse(
    file: str | Path,
    pattern: str,
    *,
    cast: dict[str, type] | None = None,
    chunk_size: int = 8192,
) -> Iterator[dict[str, Any]]
```

Reads a text log file line by line and yields the named groups of `pattern` for each line that matches (`re.match()`). Other lines are skipped. `cast` converts groups by name; values that fail to convert are kept as strings. `file` must be a path, not an open file.

```python
from logust import parse

for record in parse("app.log", r"(?P<time>[\d-]+ [\d:.]+) \| (?P<level>\w+)\s+\| (?P<message>.*)"):
    print(record["level"], record["message"])
```

### parse_json() { #parse-json }

```python
parse_json(file: str | Path, *, strict: bool = False) -> Iterator[dict[str, Any]]
```

Yields one dict per line of a JSON lines file (such as one written with `serialize=True`). Blank lines are skipped. Invalid lines are skipped, or raise `ValueError` with `strict=True`.

See [Parsing Logs](../advanced/parsing.md).

---

## Contrib { #contrib }

Optional helpers built on top of the core logger.

```python
from logust.contrib import (
    InterceptHandler,
    TailSampler,
    add_event_fields,
    canonical_event,
    clear_event_fields,
    debug_fn,
    get_current_event,
    get_event_fields,
    intercept_logging,
    log_fn,
)
# With Starlette installed, also: RequestLoggerMiddleware, get_request_id, setup_fastapi
```

### Interception { #interception }

```python
InterceptHandler(target: Logger | None = None)
intercept_logging(level: int = logging.DEBUG, target: Logger | None = None) -> None
```

* `InterceptHandler` is a `logging.Handler` that forwards `logging` records to `target` (default: the global `logger`), with the level name, the formatted message and the traceback. Records have no caller fields. A record whose level name is not a registered Logust level raises `ValueError`.
* `intercept_logging()` sets an `InterceptHandler` as the only handler of the root logger, sets the root level to `level`, and removes the handlers of all existing loggers (making them propagate).

See [Intercept Standard Logging](../how-to/intercept-standard-logging.md).

### Function timing { #function-timing }

```python
log_fn(fn=None, *, level: str = "INFO")
debug_fn(fn=None)
```

Decorators for sync and `async def` functions. After each successful call, they log `Called <name> with elapsed_time=<seconds>` (3 decimals) at `level` (`debug_fn`: `DEBUG`), reporting the caller's location. Use `@log_fn`, `@log_fn(level="...")`, `@debug_fn` or `@debug_fn()`.

See [Function Timing Decorators](../how-to/timing-decorators.md).

### Canonical events { #canonical-events }

```python
canonical_event(fields: Mapping[str, Any] | None = None) -> ContextManager[dict[str, Any]]
add_event_fields(fields: Mapping[str, Any] | None = None, **kwargs) -> bool
get_event_fields() -> dict[str, Any]
get_current_event() -> MutableMapping[str, Any] | None
clear_event_fields() -> bool
```

| Function | Description |
|----------|-------------|
| `canonical_event(fields)` | Context manager that makes a new event dict (a copy of `fields`) the current one, and yields it. Nested contexts restore the previous event. |
| `add_event_fields(fields, **kwargs)` | Updates the current event. Returns `False` (and does nothing) outside of an event. |
| `get_event_fields()` | A copy of the current event, or `{}`. |
| `get_current_event()` | The current event dict itself, or `None`. |
| `clear_event_fields()` | Empties the current event. Returns `False` outside of an event. |

The current event is stored in a `ContextVar`, so it follows `asyncio` tasks.

```python
TailSampler(
    rate: float = 1.0,
    always_keep_errors: bool = True,
    slow_ms: float | None = None,
    keep_if: Callable[[Mapping[str, Any]], bool] | None = None,
    random_fn: Callable[[], float] = random.random,
)
TailSampler.should_keep(event: Mapping[str, Any]) -> bool
```

A frozen dataclass. `should_keep()` returns `True` when `keep_if(event)` is true, or `always_keep_errors` and the event is an error (`status_code` ≥ 500, `outcome == "error"`, or an `error.type` key), or `duration_ms` ≥ `slow_ms`; otherwise it keeps a `rate` fraction (`random_fn() < rate`). Raises `ValueError` if `rate` is not between `0.0` and `1.0` or `slow_ms` is negative, and `TypeError` if `keep_if` or `random_fn` is not callable.

See [Canonical Events](../advanced/canonical-events.md).

### FastAPI / Starlette { #fastapi-starlette }

Requires `pip install "logust[fastapi]"` or `"logust[starlette]"`. Importing `logust.contrib.starlette` without Starlette raises `ImportError`.

```python
from logust.contrib.starlette import RequestLoggerMiddleware, get_request_id, setup_fastapi
```

```python
RequestLoggerMiddleware(
    app,
    *,
    skip_routes: Sequence[str] | None = None,
    skip_regexes: Sequence[str] | None = None,
    include_request_body: bool = False,
    max_body_size: int = 1000,
    mask_sensitive_data: bool = True,
    logger: Logger | None = None,
    canonical: bool = False,
    sample_rate: float = 1.0,
    slow_ms: float | None = None,
    always_keep_errors: bool = True,
    sampler: TailSampler | Callable[[Mapping[str, Any]], bool] | None = None,
)
```

| Parameter | Description |
|-----------|-------------|
| `skip_routes` | Path prefixes that are not logged. |
| `skip_regexes` | Regular expressions (`re.match()`) for paths that are not logged. |
| `include_request_body` | Log the body of `POST`, `PUT`, `PATCH` and `DELETE` requests. |
| `max_body_size` | Logged bodies are cut to this many characters. `ValueError` if negative. |
| `mask_sensitive_data` | Replace sensitive values in JSON bodies and query parameters with `"***"`. |
| `logger` | The Logust logger to use. Default: the global `logger`. |
| `canonical` | Log one `http.request` event per request instead of start / response lines. |
| `sample_rate`, `slow_ms`, `always_keep_errors` | Build a `TailSampler(rate=sample_rate, slow_ms=slow_ms, always_keep_errors=always_keep_errors)` for canonical events. |
| `sampler` | A `TailSampler` or predicate; replaces the three options above. `TypeError` if not callable. |

```python
setup_fastapi(
    app,
    *,
    skip_routes: Sequence[str] | None = None,
    skip_regexes: Sequence[str] | None = None,
    include_request_body: bool = False,
    intercept_logging: bool = True,
    canonical: bool = False,
    sample_rate: float = 1.0,
    slow_ms: float | None = None,
    always_keep_errors: bool = True,
    sampler: TailSampler | Callable[[Mapping[str, Any]], bool] | None = None,
) -> None
```

Adds `RequestLoggerMiddleware` with these options and, with `intercept_logging=True`, calls [`intercept_logging()`](#interception).

```python
get_request_id() -> str
```

The ID of the current request, or `""` outside of a request. The middleware uses the `X-Request-ID` header (sanitized, at most 128 characters) or generates an 8-character ID, and binds it as `extra["request_id"]` (with `extra["path"]`) while the request is handled.

See [FastAPI and Starlette](../how-to/fastapi.md).
