# Migrate from loguru { #migrate-from-loguru }

Logust follows the <a href="https://github.com/Delgan/loguru" class="external-link" target="_blank">loguru</a> API, so for most code, migrating is **changing one import**.

This page lists what stays the same, and the small differences you may hit when you port a bigger loguru setup.

## Change the import { #change-the-import }

//// tab | loguru

```python
from loguru import logger

logger.add("app.log", rotation="500 MB")
logger.info("Hello")
```

////

//// tab | logust

```python
--8<-- "docs_src/how_to_migrate_from_loguru/tutorial001.py"
```

////

`logger.add()` and its common options (`level`, `format`, `filter`, `rotation`, `retention`, `compression`, `serialize`, `enqueue`, `colorize`, `backtrace`, `diagnose`, `catch`), `bind()`, `contextualize()`, `patch()`, `opt()`, `catch()`, `level()`, `configure()`, `enable()` / `disable()`, `complete()` and `parse()` work the way you know.

The rest of this page goes through the differences, by topic.

## Keyword arguments and `extra` { #keyword-arguments-and-extra }

`logger.info("{} by {user}", "login", user="alice")` formats the message the same way in both libraries.

The difference is in `extra`. loguru copies **every** keyword argument into `extra`. Logust only adds the ones that are **not** used by a placeholder in the message:

```python hl_lines="8"
--8<-- "docs_src/how_to_migrate_from_loguru/tutorial002.py"
```

//// tab | loguru

```text
login by alice | extra={'user': 'alice', 'ip': '10.0.0.7'}
```

////

//// tab | logust

```text
login by alice | extra={'ip': '10.0.0.7'}
login by alice | extra={'user': 'alice'}
```

////

If you want a value both in the message and in `extra`, `bind()` it, as in the second call.

`opt(capture=False)` keeps **every** keyword argument out of `extra`, in both libraries. Read more in [Message Arguments](../tutorial/message-arguments.md#extra-keyword-arguments-go-to-extra).

## `contextualize()` { #contextualize }

`contextualize()` is **context-local** in both libraries: the values live in a `contextvars` variable, so each thread and asyncio task sees only its own blocks. The precedence is the same too: `contextualize()` values, then `bind()` values, then the message's keyword arguments, later sources winning. See [Adding Context](../tutorial/context.md#precedence).

There are a few small differences:

* Logust's `contextualize()` yields the logger, so `with logger.contextualize(...) as log:` works. loguru's yields `None`.
* `configure(extra=...)` **binds** the values to the logger in Logust, so they override `contextualize()` values with the same key, like `bind()` does. In loguru they are the core defaults, and `contextualize()` overrides them.
* A block entered in one `contextvars` context and exited in another (for example, an async generator closed by another task) restores the previous values, instead of raising `ValueError` as loguru does.

## Callable sinks receive no trailing newline { #callable-sinks-receive-no-trailing-newline }

loguru passes callable sinks the formatted message **with** a trailing `"\n"`, so loguru recipes often use `end=""`. Logust passes it **without** one, so drop `end=""` when you port them:

//// tab | loguru

```python
logger.add(lambda msg: tqdm.write(msg, end=""))
logger.add(lambda msg: print(msg, end=""))
```

////

//// tab | logust

```python
logger.add(lambda msg: tqdm.write(msg))
logger.add(lambda msg: print(msg))
```

////

If you keep `end=""` with Logust, all your log lines are joined into one (see [Progress Bars](progress-bars.md#dont-pass-end)).

Stream sinks (objects with a `write()` method, like `sys.stdout` or `io.StringIO`) get a trailing newline in both libraries.

Also, a loguru callable sink gets a `str` subclass with a `.record` attribute. A Logust callable sink gets a plain `str`. If you need the record, use [`add_callback()`](../advanced/callbacks.md).

## Format strings { #format-strings }

loguru format strings work as they are, including `{time:YYYY-MM-DD}`, `{level.icon}`, `{thread.name}` and `{file.path}` (see [Format tokens](../tutorial/formatting.md#format-tokens)). The differences:

* **`{exception}`** places the traceback once, where you put it. loguru appends `"\n{exception}"` to every string format, so a loguru format that contains `{exception}` prints it twice.
* **Plain `{time}`** gives `2026-10-06 12:00:00.123` on the console and in files (loguru: ISO 8601). Use `{time:}` for ISO 8601. In callable sinks, plain `{time}` gives ISO 8601 with microseconds.
* **`{thread}` and `{process}`** give `name:id`, like `MainThread:8348778368` (loguru: the id). Use `{thread.id}` / `{process.id}` for the id.
* The **`zz`** time token gives the UTC offset (`+09:00`) instead of a time zone abbreviation, except with `!UTC`.
* **`{extra}`** sorts the keys (loguru keeps the binding order), and writes values other than `str`, numbers, `bool`, `None`, lists, tuples and dicts with `str()` instead of `repr()`.

## Exceptions { #exceptions }

* **`backtrace` and `diagnose`**: `add()` accepts both, as in loguru, but both are `False` by default. loguru defaults to `True`, which writes variable values (possibly secrets 🚨) into your logs. Pass them explicitly if you want loguru's level of detail. See [Tracebacks](../advanced/tracebacks.md).
* **Traceback style**: `diagnose=True` lists the variables used on each line as `| name = value`, instead of loguru's annotated source lines. `backtrace=True` adds the outer frames without loguru's `⥤` marker. Tracebacks are not colorized.
* `opt(backtrace=True)` and `opt(diagnose=True)` are **Logust additions**: they turn the detail on for one message, on every handler.

## Message markup and `opt()` { #message-markup-and-opt }

* **`opt(colors=...)`**: loguru parses color markup in a message only with `opt(colors=True)`. Logust **always** parses it (and strips it on sinks without colors), so `colors=True` changes nothing, and `colors=False` keeps the tags as plain text for that message.
* **`opt(capture=False)`** works as in loguru.
* **`opt(raw=True)`** and **`opt(record=True)`** are not supported yet: they raise `TypeError`.

//// tab | loguru

```python
logger.opt(colors=True).info("<red>Error</red> in <blue>module</blue>")
```

////

//// tab | logust

```python
logger.info("<red>Error</red> in <blue>module</blue>")
```

////

Read more in [Per-message Options with opt()](../advanced/opt.md).

## Record dicts in filters, patchers, and callbacks { #record-dicts-in-filters-patchers-and-callbacks }

Filters, patchers and [`add_callback()`](../advanced/callbacks.md) callbacks get a record with loguru's keys: `record["level"].no`, `record["time"]` (an aware `datetime`), `record["elapsed"]` (a `timedelta`), `record["file"].path`, `record["thread"].id`, `record["process"].name`, `record["module"]`, and so on. See [The record dict](../tutorial/filters.md#the-record-dict).

The differences:

* `record["exception"]` is the traceback **text**, or `None`. It's not a `(type, value, traceback)` tuple.
* `record["level"]` and `record["file"]` are also strings: `record["level"] == "INFO"` is true. The record also keeps Logust's flat keys (`level_no`, `timestamp`, `thread_id`, ...).
* A patcher's record has no caller fields (`name`, `module`, `function`, `line`, `file`), and only its changes to `message`, `extra` and `exception` are used.
* The **values in `record["extra"]` are strings**: loguru keeps the original objects.

Let's see the last one:

```python
--8<-- "docs_src/how_to_migrate_from_loguru/tutorial003.py"
```

//// tab | loguru

```text
{'order_id': 1234, 'total': 9.99, 'tags': ['new']}
```

////

//// tab | logust

```text
{'total': '9.99', 'tags': "['new']", 'order_id': '1234'}
```

////

So a filter like `record["extra"]["order_id"] > 1000` needs an `int(...)` with Logust. The values keep their types in [JSON output](../tutorial/json-output.md).

## File sink options { #file-sink-options }

`compression`, `mode`, `encoding`, `delay` and `catch` use loguru's names, with these differences:

* **`compression`**: `"gz"`, `"bz2"`, `"zip"`, `"tar"`, `"tar.gz"` and `"tar.bz2"` are supported, and `True` means gzip. `"xz"`, `"lzma"` and `"tar.xz"` raise `ValueError`. A compression function raises `TypeError`.
* **`mode`**: only `"a"` and `"w"` are supported. Others raise `ValueError`.
* **`encoding`**: files are always written as UTF-8. UTF-8 aliases are accepted; other encodings raise `ValueError`.
* **`catch`**: loguru defaults to `catch=True`, which prints sink errors to stderr. Logust defaults to `catch=None`, which drops them silently. Pass `catch=True` for loguru's behavior, or `catch=False` to raise the error from the logging call. See [Sink Errors](../advanced/sink-errors.md).
* **Rotated file names** follow Logust's `app.<timestamp>.pid<pid>.log` pattern, with the archive extension appended (for example `.log.zip`). See [Rotated file names](../tutorial/rotation-retention.md#rotated-file-names).
* **`buffering`** and the other `open()` arguments are not supported: they raise `TypeError`. Like loguru's default (line buffering), each line is in the file when the logging call returns; for batched writes, use `enqueue=True`.
* **Time-based `rotation`**: `timedelta(days=1)`, `timedelta(hours=1)` and `time(0, 0)` are supported, and rotate on clock boundaries (midnight, top of the hour, local time, daylight saving changes handled like loguru). Other intervals and times raise `ValueError`.
* **`rotation` and `retention` strings**: sizes (`"500 MB"`), `"daily"` / `"1 day"` and `"hourly"` / `"1 hour"` for rotation, and a number of days (`"10 days"`) for retention. loguru also accepts values like `"1 week"`, `"monday at 12:00"`, `"2 months"` or functions; in Logust, unsupported strings raise `ValueError` when you call `add()`. See [All rotation values](../tutorial/rotation-retention.md#all-rotation-values).

`mode`, `encoding` and `delay` only apply to file sinks; passing them for another sink raises `TypeError`.

## Other differences { #other-differences }

* **`catch()`**: same call shapes as loguru (`@logger.catch`, `@logger.catch(...)`, `with logger.catch():`) and the same `exception`, `level`, `reraise`, `onerror`, `exclude` and `default` options. The message is `"An error occurred: <exception>"` (change the prefix with `message=`), not loguru's `"An error has been caught in function ..."`.
* **`level()`**: returns `Level(name, no, color, icon)` like loguru, but `color` is a color name (`"green"`) rather than markup (`"<green><bold>"`). Level names are case-insensitive. Passing a new `no` for an existing **custom** level re-registers it instead of raising; for a built-in level it raises `TypeError`, as in loguru.
* **Coroutine sinks**: `async def` sinks are not supported yet. `add()` raises `TypeError` instead of silently never awaiting them.
* **`enable()` / `disable()`**: `enable("mylib")` and `disable("mylib")` follow loguru (prefix match on the dotted module name, most specific rule wins, `""` means all modules). **Without a name**, or with a built-in level name such as `enable("INFO")`, they keep Logust's meaning: they turn the console handler off and on. loguru has no such form. Records from [`InterceptHandler`](intercept-standard-logging.md) are matched against the `logging` logger name. See [Logging in Libraries](../advanced/library-logging.md).
* **`logger.parse()`**: the same as `logust.parse()`. It takes a file path (not an open file), and `cast` must be a dict. See [Parsing Logs](../advanced/parsing.md).

## Recap { #recap }

* Change `from loguru import logger` to `from logust import logger`; the common API is the same.
* Keyword arguments used by the message don't go to `extra`; `bind()` them if you need both.
* Drop `end=""` in callable sinks.
* `backtrace` and `diagnose` are off by default; turn them on explicitly.
* Message markup is always parsed; `opt(raw=...)` and `opt(record=...)` are not available.
* `record["exception"]` is text, and `record["extra"]` values are strings in filters, patchers and callbacks.
* `contextualize()` is context-local as in loguru, but yields the logger, and `configure(extra=...)` values win over it.
* Some file options have a smaller set of values: no `xz` compression, `"a"` / `"w"` modes only, UTF-8 only, and fewer `rotation` / `retention` strings (others raise `ValueError`).
