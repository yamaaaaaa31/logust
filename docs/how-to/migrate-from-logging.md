# Migrate from logging { #migrate-from-logging }

The standard `logging` module is very configurable, but it asks for a lot of setup: loggers, handlers, formatters, levels on each of them. This page shows how the usual `logging` code maps to Logust, so you can move an existing project step by step.

## Why move { #why-move }

Compared to the standard `logging` module, Logust gives you:

1. **Zero configuration**: one import, and you get readable, colored output with time, level and caller.
2. **Better performance** out of the box: formatting and file writes run in Rust. See the [Benchmarks](../about/benchmarks.md).
3. **A simpler API**: one `logger` object, and handlers you add with one call.
4. **Built-in rotation, retention, compression, colors and JSON**, without extra handler classes.

## A first migration { #a-first-migration }

Here's a typical `logging` setup that writes to the console and to a file, next to the same thing with Logust:

//// tab | logging

```python
--8<-- "docs_src/how_to_migrate_from_logging/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:05:50,873 | INFO | Hello
```

</div>

////

//// tab | logust

```python
--8<-- "docs_src/how_to_migrate_from_logging/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:05:50.948 | INFO     | __main__:<module>:4 - Hello
```

</div>

////

With Logust, the console handler is already there, so you only add the file. Both lines, the console one and the one in `app.log`, use the default format with the caller (`__main__:<module>:4`).

There's no `getLogger(__name__)`: you import the same `logger` everywhere, and the module name is filled in for you as `{name}`.

## Messages, context and exceptions { #messages-context-and-exceptions }

The everyday calls change a bit:

//// tab | logging

```python
--8<-- "docs_src/how_to_migrate_from_logging/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

INFO:__main__:User alice logged in from 10.0.0.7
INFO:__main__:Payment received
ERROR:__main__:Calculation failed
Traceback (most recent call last):
  File "/home/user/code/main.py", line 11, in <module>
    1 / 0
    ~~^~~
ZeroDivisionError: division by zero
```

</div>

////

//// tab | logust

```python
--8<-- "docs_src/how_to_migrate_from_logging/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:05:51.036 | INFO     | __main__:<module>:4 - User alice logged in from 10.0.0.7
2026-10-06 12:05:51.036 | INFO     | __main__:<module>:5 - Payment received
2026-10-06 12:05:51.036 | ERROR    | __main__:<module>:10 - Calculation failed
Traceback (most recent call last):
  File "/home/user/code/main.py", line 8, in <module>
    1 / 0
    ~~^~~
ZeroDivisionError: division by zero
```

</div>

////

* **Arguments** use `{}` placeholders (`str.format()` style) instead of `%s`. See [Message Arguments](../tutorial/message-arguments.md).
* **Context** goes in `bind()` instead of `extra={...}`. See [Adding Context](../tutorial/context.md).
* **`logger.exception()`** works the same: call it in an `except` block to log the traceback. See [Logging Exceptions](../tutorial/exceptions.md).

/// warning | `%s` is not replaced

Logust doesn't know about `%`-style placeholders. They are left as they are:

```python
--8<-- "docs_src/how_to_migrate_from_logging/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:05:51.082 | INFO     | __main__:<module>:3 - User %s logged in
```

</div>

Search your code for `%s`, `%d`, `%r` and `%(` in log calls when you migrate.

///

## Rotating files { #rotating-files }

`RotatingFileHandler` and `TimedRotatingFileHandler` become options of `logger.add()`:

```python
--8<-- "docs_src/how_to_migrate_from_logging/tutorial006.py"
```

* `rotation="10 MB"` replaces `maxBytes`, and `retention=5` replaces `backupCount`.
* `rotation="daily"` replaces `TimedRotatingFileHandler(when="midnight")`, and `retention="7 days"` keeps a week of files.

You can also compress the old files with `compression`. Read all about it in [Rotation, Retention and Compression](../tutorial/rotation-retention.md).

## Cheat sheet { #cheat-sheet }

| `logging` | Logust |
|-----------|--------|
| `logger = logging.getLogger(__name__)` | `from logust import logger` |
| `logger.info("x=%s", x)` | `logger.info("x={}", x)` |
| `logger.info("msg", extra={"k": v})` | `logger.bind(k=v).info("msg")` |
| `logging.LoggerAdapter(logger, {"k": v})` | `logger.bind(k=v)` |
| `logger.exception("msg")` | `logger.exception("msg")` |
| `logger.error("msg", exc_info=True)` | `logger.opt(exception=True).error("msg")` |
| `logging.basicConfig(level=logging.INFO)` | `logger.set_level("INFO")` |
| `handler.setLevel(logging.WARNING)` | `logger.add(sink, level="WARNING")` |
| `logging.Formatter("%(asctime)s %(message)s")` | `logger.add(sink, format="{time} {message}")` |
| `logging.FileHandler("app.log")` | `logger.add("app.log")` |
| `RotatingFileHandler(maxBytes=..., backupCount=...)` | `logger.add("app.log", rotation="10 MB", retention=5)` |
| `TimedRotatingFileHandler(when="midnight")` | `logger.add("app.log", rotation="daily")` |
| `logging.StreamHandler(sys.stderr)` | `logger.add(sys.stderr)` |
| `logging.Filter` subclass | `logger.add(sink, filter=lambda record: ...)` |
| `logging.addLevelName(25, "NOTICE")` | `logger.level("NOTICE", no=25)` |
| `logging.config.dictConfig({...})` | `logger.configure(handlers=[...], levels=[...])` |
| `logging.getLogger("lib").setLevel(logging.CRITICAL)` | `logger.disable("lib")` |
| A JSON formatter library | `logger.add(sink, serialize=True)` |

Logust's built-in levels are the same numbers as `logging` (`DEBUG` 10, `INFO` 20, `WARNING` 30, `ERROR` 40, `CRITICAL` 50), plus `TRACE` (5), `SUCCESS` (25) and `FAIL` (45). See [Log Levels](../tutorial/log-levels.md).

## Third-party libraries { #third-party-libraries }

Your dependencies keep using `logging`, and that's fine. Route their records through Logust with one call, as explained in [Intercept Standard Logging](intercept-standard-logging.md):

```python
from logust.contrib import intercept_logging

intercept_logging()
```

This also lets you migrate gradually: modules you haven't moved yet keep calling `logging`, and their messages still end up in your Logust handlers.

## Recap { #recap }

* Import `logger` from `logust` instead of creating loggers with `getLogger()`.
* Replace `%s` placeholders with `{}`, and `extra=` with `bind()`.
* Handlers, formatters, levels and rotation become arguments of `logger.add()`.
* `dictConfig()` becomes `logger.configure()`.
* Use `intercept_logging()` for third-party libraries and for code you haven't migrated yet.
