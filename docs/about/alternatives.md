# Alternatives and Comparison { #alternatives-and-comparison }

Logust is not the only way to log in Python. Here's how it compares to the two options you are most likely considering: <a href="https://github.com/Delgan/loguru" class="external-link" target="_blank">loguru</a> and the standard `logging` module.

## At a glance { #at-a-glance }

### Logust { #logust }

* A Rust core, with high throughput.
* The loguru-style API.
* Rotation, retention, compression, JSON and background writes built in.

### loguru { #loguru }

* The library whose API Logust follows.
* Rich sink options, like coroutine sinks and `opt(record=True)`.
* A long-established ecosystem and many recipes online.

### logging { #logging }

* Part of the standard library: always available, and every library uses it.
* Very configurable, but verbose.
* Slower by default.

## Feature comparison { #feature-comparison }

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
| Coroutine (`async def`) sinks | No | Yes |
| `opt(raw=True)` / `opt(record=True)` | No | Yes |
| Stack info (module, function, line) | Yes | Yes |
| Process / thread info | Yes | Yes |
| Format fields (`{time:<spec>}`, `{level.icon}`, `{file.path}`, `{exception}`, ...) | Yes | Yes |
| Per-module `enable(name)` / `disable(name)` | Yes | Yes |
| loguru-shaped records in filters and patchers (`record["level"].no`, `record["time"]`, ...) | Yes | Yes |
| Standard `logging` interception | Yes (`intercept_logging()`) | Recipe in the docs |
| FastAPI / Starlette middleware | Yes (`logust.contrib`) | No |

The details of every difference are in [Migrate from loguru](../how-to/migrate-from-loguru.md).

## Performance { #performance }

For 10,000 messages written to a file, Logust takes around **16 ms**, the standard `logging` module around **960 ms**, and loguru around **2.7 s** in the benchmark suite of the repository.

See all the numbers, and how to run them yourself, in [Benchmarks](benchmarks.md).

## Logust vs standard logging { #logust-vs-standard-logging }

The advantages of Logust over the standard `logging` module:

1. **Zero configuration** with readable defaults.
2. **Better performance** out of the box.
3. **A simpler API** with fewer moving parts: no loggers, handlers and formatters to wire together.
4. **Built-in** rotation, retention, compression, colors and JSON.

And you don't have to choose for your dependencies: they keep using `logging`, and you can [route their logs through Logust](../how-to/intercept-standard-logging.md).

Here is the same setup in both:

//// tab | logging

```python
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
```

////

//// tab | logust

```python
from logust import logger

logger.add("app.log")
logger.info("Hello")
```

////

For a step by step guide, see [Migrate from logging](../how-to/migrate-from-logging.md).

## When to choose which { #when-to-choose-which }

### Choose Logust { #choose-logust }

* When performance and throughput matter: busy services, batch jobs, lots of log lines.
* When you want the loguru-style API with a fast core.
* When you need rotation, retention, JSON, callable sinks and background writes without extra packages.
* When you run FastAPI or Starlette and want request logging and canonical events ready to use.

### Choose loguru { #choose-loguru }

* When you need full loguru compatibility for advanced features, like coroutine sinks, `opt(raw=True)`, `opt(record=True)`, or exception tuples in records.
* When you need compression formats or file encodings that Logust doesn't support.

### Choose logging { #choose-logging }

* When you write a **library** and don't want to add any dependency. (If your library uses Logust, see [Logging in Libraries](../advanced/library-logging.md).)
* When you depend on tooling that is built around `logging` handlers and formatters.
