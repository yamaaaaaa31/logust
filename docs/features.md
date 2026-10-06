# Features { #features }

## Logust Features { #logust-features }

**Logust** gives you the following:

### Based on the loguru API { #based-on-the-loguru-api }

If you know <a href="https://github.com/Delgan/loguru" class="external-link" target="_blank">loguru</a>, you already know Logust.

* One global `logger`, ready to use. No `getLogger()`, no handler or formatter classes.
* `logger.add()` to add a sink, `logger.remove()` to remove it.
* `bind()`, `contextualize()`, `patch()`, `opt()`, `catch()`, `level()`, `enable()` / `disable()`, `parse()`...

For most code, migrating is changing the import:

```python
# from loguru import logger
from logust import logger
```

/// tip

There are some small differences. Check [Migrate from loguru](how-to/migrate-from-loguru.md) for the full list.

///

### Fast, with a Rust core { #fast-with-a-rust-core }

The parts of logging that run for every message, formatting, JSON serialization and writing to files, are implemented in Rust.

Writing 10,000 messages to a file takes around **16 ms** with Logust, versus around **960 ms** with the standard `logging` and **2.7 s** with loguru. See the [Benchmarks](about/benchmarks.md).

On top of that, Logust only collects what your format needs. If your format doesn't show the caller (`{name}`, `{function}`, `{line}`...), Logust doesn't inspect the stack at all. More on that in [Performance](advanced/performance.md).

### Beautiful by default { #beautiful-by-default }

With zero configuration you get colored, aligned output with the time, level and caller of every message. For the sinks you add, color is detected automatically, and `NO_COLOR` / `FORCE_COLOR` are respected.

You can also use color markup in your formats and messages, like `<red>`, `<bold>` or `<level>`. See [Formatting](tutorial/formatting.md).

### Sinks: console, files, or anything { #sinks-console-files-or-anything }

A **sink** is where your logs go. It can be:

* `sys.stdout` or `sys.stderr`.
* A file path, as a `str` or `pathlib.Path`.
* Any Python callable, like a function or a method.

Each sink has its own level, format, filter, colors and options. See [Handlers and Sinks](tutorial/sinks.md).

### Log files done right { #log-files-done-right }

All the things you need for files in production, as keyword arguments:

* **Rotation** by size (`"500 MB"`) or by time (`"daily"`, `"1 hour"`...).
* **Retention** by age (`"30 days"`) or by number of files.
* **Compression** of rotated files: `gz`, `bz2`, `zip`, `tar`, `tar.gz`, `tar.bz2`.
* **Background writes** with `enqueue=True`, so logging doesn't block your code.
* `mode`, `encoding` and `delay`, like the standard `open()`.

See [Logging to Files](tutorial/file-output.md) and [Rotation, Retention and Compression](tutorial/rotation-retention.md).

### Structured logging { #structured-logging }

* `serialize=True` writes one JSON object per line, ready for your log aggregator. See [JSON Output](tutorial/json-output.md).
* `bind()` attaches context to a logger, and `contextualize()` attaches it to everything logged inside a `with` block, safely across threads and `asyncio` tasks. See [Adding Context](tutorial/context.md).
* Keyword arguments to log calls also end up in the record's `extra`.

### Exceptions { #exceptions }

* `logger.exception()` logs the current exception with its full traceback.
* `@logger.catch()` logs any exception raised in a function or a `with` block.
* `backtrace` and `diagnose` show the values of the variables in each frame, per sink.

See [Logging Exceptions](tutorial/exceptions.md) and [Traceback Detail](advanced/tracebacks.md).

### Integrations { #integrations }

* **Standard `logging`**: route everything, including third-party libraries, through Logust. See [Intercept Standard Logging](how-to/intercept-standard-logging.md).
* **FastAPI and Starlette**: request logging middleware with request IDs and sensitive data masking. See [FastAPI and Starlette](how-to/fastapi.md).
* **Canonical events**: one wide, structured event per request, with tail sampling. See [Canonical Events](advanced/canonical-events.md).
* **Progress bars**: play nicely with `rich` and `tqdm`. See [Progress Bars](how-to/progress-bars.md).

### Ready for modern Python { #ready-for-modern-python }

* Python 3.10+.
* Fully typed, with type stubs for the Rust extension.
* Wheels for free-threaded CPython (3.13t and 3.14t) on Linux and macOS. See [Threads and Processes](advanced/threads-and-processes.md).
