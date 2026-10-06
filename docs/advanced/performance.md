# Performance { #performance }

Logust is fast by default: records are formatted and written in Rust, and you don't have to do anything to get that. 🚀

But if logging is on a really hot path, it helps to know **where the time goes**, and the few knobs you can turn.

## Caller information is the expensive part { #caller-information-is-the-expensive-part }

To know the module, function and line of a log call, Logust has to inspect the Python **call stack**. That's the most expensive part of a log call. The same goes, to a lesser extent, for the thread and the process.

So Logust only collects them when they are **needed**. When you add a handler, it reads the format and checks which fields it uses. Let's measure it:

```python hl_lines="8-9"
--8<-- "docs_src/advanced_performance/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

without caller  0.71 µs per message
with caller     1.27 µs per message
```

</div>

The only difference is `{name}:{function}:{line}` in the format. Without it, Logust doesn't look at the call stack at all.

This works for every kind of sink: files, the console, and callable sinks. For a callable sink, `logger.add(fn, format="{time} | {level} - {message}")` doesn't collect caller information either.

/// info

The information is collected **once per message**, and shared by all the handlers. So if one handler needs the caller, every handler pays for it. To keep the fast path, all of your handlers need to skip the caller fields.

Filter functions (`filter=`) and [callbacks](callbacks.md) receive the full record, so a handler with a filter function, or a callback, also makes Logust collect everything. A [string or dict filter](../tutorial/filters.md#filter-by-module) only needs the module name, so it only turns on the caller lookup.

///

## CollectOptions { #collectoptions }

The automatic detection is right most of the time. If you want to decide yourself, pass a `CollectOptions` to `logger.add(collect=...)`.

It has three fields, `caller`, `thread` and `process`, and each one can be:

| Value | Meaning |
|-------|---------|
| `None` (default) | Detect from the format. |
| `False` | Never collect: the fields are empty. |
| `True` | Always collect, even if the format doesn't use them. |
| `CallerInfo(...)` / `ThreadInfo(...)` / `ProcessInfo(...)` | Use these **fixed** values, without looking anything up. |

### Turn collection off { #turn-collection-off }

With `False`, the information is never collected, even if the format uses it:

```python hl_lines="9"
--8<-- "docs_src/advanced_performance/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

::0 |  | Request handled
```

</div>

The caller and thread fields are empty, and `{line}` is `0`. That's useful for a shared format string, when you know that a fast handler doesn't need those fields.

### Fixed values { #fixed-values }

You can also give the values yourself. Logust then uses them as they are, which costs nothing per message:

```python hl_lines="9-13"
--8<-- "docs_src/advanced_performance/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

billing:worker | billing-loop | billing | Invoice sent
```

</div>

That's handy for a service where every message comes from the same place, but the log format (shared with other services) expects these fields.

The constructors are:

```python
from logust import CallerInfo, ProcessInfo, ThreadInfo

CallerInfo(name="mymodule", function="handler", line=42, file="handler.py")
ThreadInfo(name="WorkerThread", id=12345)
ProcessInfo(name="MainProcess", id=1234)
```

### Always collect { #always-collect }

`True` forces the collection, even if the format doesn't use the fields:

```python
logger.add("full.log", collect=CollectOptions(caller=True, thread=True, process=True))
```

## Performance tips { #performance-tips }

1. **Keep hot-path formats simple.** Skip `{name}`, `{function}`, `{line}` and `{file}` in formats where you don't need them, in **all** the handlers. That includes the default console handler: its format shows the caller, so call `logger.remove()` before adding your own handlers. Only the handlers that accept a message's level count, so an `ERROR`-only handler with `{line}` doesn't slow down your `INFO` messages.
2. **Avoid filter functions and callbacks on hot paths.** They need the full record, so they turn the caller lookup back on. To filter by module, use a string or dict filter: it is checked in Rust, without a Python call.
3. **Use `CollectOptions`** to turn off what you don't need, or to provide fixed values.
4. **Skip work for hidden messages.** Use [`opt(lazy=True)`](opt.md#lazy-evaluation) or `logger.is_level_enabled()` to avoid computing values for messages that won't be written.
5. **Use `enqueue=True`** when a slow disk must not block your code (see [Async Writes](async-writes.md)). It doesn't make Logust faster, it moves the I/O to another thread.
6. **Keep the default buffering on hot paths.** `buffering=1` (one `write()` system call per line, like loguru) makes every line survive a kill, but the system call is most of the time of a file log call: about 2.5 µs per message instead of 0.9 µs with the default format, on an Apple Silicon Mac. Use it where losing the last lines on a kill matters more. See [When it's written](../tutorial/file-output.md#make-sure-its-written).

For numbers comparing Logust with loguru and the standard `logging` module, see [Benchmarks](../about/benchmarks.md).

## Recap { #recap }

* Looking up the caller is the most expensive part of a log call.
* Logust reads your formats and only collects what they use.
* The information is collected once per message, for all handlers, and filter functions and callbacks need everything.
* `CollectOptions` turns collection off, forces it on, or provides fixed values.
