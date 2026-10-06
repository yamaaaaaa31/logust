# About { #about }

About Logust, its design, inspiration and more. 🤓

## Why Logust exists { #why-logust-exists }

<a href="https://github.com/Delgan/loguru" class="external-link" target="_blank">loguru</a> made logging in Python pleasant: one `logger`, no boilerplate, nice output by default. But every message still goes through pure Python code for formatting, serialization and writing, and that cost adds up in services that log a lot.

The standard `logging` module is everywhere, but it needs a lot of setup, and it's not fast either.

Logust is the attempt to have **both**: the API you already like from loguru, and a hot path fast enough that you don't have to think about the cost of a log line.

## The design { #the-design }

Logust has two layers:

* A **Rust core** (built with <a href="https://pyo3.rs" class="external-link" target="_blank">PyO3</a>) that does the work for every message: level checks, formatting, color markup, JSON serialization, file writes, rotation, retention, compression and background writes.
* A thin **Python layer** with the loguru-style API: `logger.add()`, `bind()`, `contextualize()`, `opt()`, `catch()`, `patch()`, filters and callbacks, plus the integrations in `logust.contrib`.

Two ideas guide the implementation:

* **Only collect what you use.** Logust reads your formats when you add a handler. If no handler shows the caller, thread or process, it doesn't inspect the stack for them. See [Performance](../advanced/performance.md).
* **Safe defaults.** For example, tracebacks don't include variable values unless you ask for them, because they can contain secrets. See [Tracebacks](../advanced/tracebacks.md).

## In this section { #in-this-section }

* [Alternatives and Comparison](alternatives.md): Logust compared with loguru and the standard `logging` module, and when to choose each.
* [Benchmarks](benchmarks.md): the numbers, and how to reproduce them.
