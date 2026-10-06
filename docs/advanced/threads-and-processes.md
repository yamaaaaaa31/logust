# Threads and Processes { #threads-and-processes }

Real apps do several things at once: web servers use thread pools, data pipelines use worker processes. Your logs should keep up, without mixed-up lines or lost messages.

Here's how Logust behaves with threads, with processes, and on free-threaded Python.

## Threads { #threads }

The `logger` is **thread-safe**. You can log from as many threads as you want, to the same sinks, without any locking on your side:

```python hl_lines="10-11 14-18"
--8<-- "docs_src/advanced_threads_and_processes/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

4000 lines, for example: worker-3 | Processed item 999
```

</div>

Four threads, 1,000 messages each: 4,000 complete lines in the file. Each message is written as a whole line, lines from different threads are never mixed together.

`{thread.name}` in the format (or `record["thread"].name` in a filter) tells you which thread logged each line. Give your threads names, it makes the logs much easier to read. 😎

/// warning | Context and concurrency

[`contextualize()`](../tutorial/context.md) currently changes the context of the **shared** logger while the `with` block runs. It is not isolated per thread or per asyncio task: a message logged by another thread (or by another task, between two `await`s) during that time gets the same values.

When several threads or tasks need their own context, use [`bind()`](../tutorial/context.md) and pass the bound logger around: a bound logger is a separate object, so its values never leak.

```python
def worker(job_id):
    log = logger.bind(job_id=job_id)
    log.info("Starting")
```

///

## Processes { #processes }

Each process has its **own** logger. What a child process starts with depends on how it's created:

* With **spawn** (the default on Windows and macOS) or **forkserver** (the default on Linux since Python 3.14), the child starts a fresh interpreter. It imports `logust` again and gets the default logger, **not** your handlers. So configure logging in the child too.
* With **fork**, the child gets a copy of the parent's logger, handlers included.

The portable way is to configure logging in a function that both the parent and the workers call:

```python hl_lines="7-9 13 21"
--8<-- "docs_src/advanced_threads_and_processes/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

1501 lines
Worker-1 | Task 1 step 0
MainProcess | All workers finished
```

</div>

Three worker processes and the parent write to the **same file**, and every line is there: 3 × 500 from the workers, plus the parent's.

A few things to notice:

* `setup_logging()` calls `logger.remove()` first, so the child doesn't keep the default console handler.
* Each worker calls `logger.complete()` before it ends, so its queued messages are written before the process exits (see [Async Writes](async-writes.md)).
* `{process.name}` shows which process wrote each line.

/// info

Several processes can append to the same log file. Logust coordinates them with a lock file next to the log (`workers.log.lock` here), so [rotation](../tutorial/rotation-retention.md) also works when several processes share a file: one process rotates, and the others follow.

///

## Fork caveats { #fork-caveats }

Forking a process that has threads is delicate in any library, and logging uses threads for `enqueue=True` sinks. Logust handles the common cases:

* A forked child can log through the sinks it inherited, and add and remove its own.
* A child created with `fork()` never starts a writer thread: `enqueue=True` sinks inherited from the parent write **synchronously** in the child.
* On macOS, `enqueue=True` sinks added **in** the forked child also write synchronously. Rust's thread parking uses libdispatch there, which crashes a forked child (`SIGTRAP`) once the parent has used it.
* A child doesn't write the parent's buffered messages a second time.

/// tip

If you can, prefer the **spawn** start method, and configure logging in each process. It works the same on every platform, and avoids the classic fork-with-threads pitfalls, in Logust and in every other library you use.

///

## Free-threaded Python { #free-threaded-python }

Python 3.13 introduced an optional **free-threaded** build (`python3.14t`), without the GIL, where threads really run in parallel.

Logust supports it: the release builds `cp314t` wheels for Linux, macOS and Windows, and the test suite runs on 3.14t in CI. Importing `logust` keeps the GIL **disabled**.

You can check it with this script, which logs from 8 threads in parallel:

```python hl_lines="7-10"
--8<-- "docs_src/advanced_threads_and_processes/tutorial003.py"
```

<div class="termy">

```console
$ python3.14t main.py

Python 3.14.7, free-threaded build: True, GIL enabled: False
16000 lines
```

</div>

The GIL is still off after `import logust`, and all 16,000 messages are in the file. 🎉

Install it as usual, `pip` picks the free-threaded wheel for a free-threaded interpreter:

<div class="termy">

```console
$ python3.14t -m pip install logust

---> 100%
```

</div>

/// note

Free-threaded wheels are built for Python **3.14t**. On other free-threaded versions, `pip` would build Logust from source, which needs a Rust toolchain.

///

## Recap { #recap }

* The logger is thread-safe, lines from different threads never get mixed.
* With spawn or forkserver, configure logging in each process. With fork, the child inherits the handlers.
* Several processes can share a log file, rotation included.
* In forked children, `enqueue=True` sinks write synchronously.
* Logust supports free-threaded Python 3.14t, and keeps the GIL disabled.
