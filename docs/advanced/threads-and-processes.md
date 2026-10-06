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

## Context in threads and tasks { #context-in-threads-and-tasks }

[`contextualize()`](../tutorial/context.md#context-local) is **context-local**: its values live in a `contextvars` variable, so each thread and each asyncio task sees only the blocks it entered itself. Two threads, or two tasks in `asyncio.gather()`, can each open their own block at the same time, and their values never mix.

There are a few details about what a new thread, a new task or a generator gets.

### New threads start empty { #new-threads-start-empty }

A new `threading.Thread` does **not** inherit the values of the block it was started in. If you want it to, run its target with `contextvars.copy_context().run()`:

```python hl_lines="18 22-23"
--8<-- "docs_src/advanced_threads_and_processes/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

MainThread | Starting the threads | {'job_id': 'j-42'}
plain | Working | {}
copied | Working | {'job_id': 'j-42'}
```

</div>

`plain` starts with an empty context. `copied` runs `work()` inside a copy of the main thread's context, so it gets the `job_id`.

/// note | Technical Details

This is how `contextvars` work in Python, not something specific to Logust. Python copies the context for new threads by itself when `sys.flags.thread_inherit_context` is set (Python 3.14+, on by default on free-threaded builds).

Thread pools like `concurrent.futures.ThreadPoolExecutor` don't pass the context of `submit()` to the function they run either. Submit `contextvars.copy_context().run` with your function as its first argument, or open the block inside the function the pool runs.

///

### Tasks inherit, and keep, the values { #tasks-inherit-the-values }

An asyncio task created **inside** a block inherits its values, because asyncio copies the current context when it creates a task. And it keeps them, even after the block that created it has ended:

```python hl_lines="16-17 19"
--8<-- "docs_src/advanced_threads_and_processes/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

Order saved | {'order_id': 1234}
Back in main() | {}
Email sent | {'order_id': 1234}
```

</div>

`"Email sent"` is logged after `main()` has left the block, and it still has the `order_id`: the task got its own copy of the context when it was created. 🤓

It also works the other way: blocks that a task opens itself never affect its parent or the other tasks.

### Generators share their caller's context { #generators-share-their-callers-context }

A generator runs in the context of the code that iterates it. So a block left open across a `yield` is visible to the caller too, until the generator resumes and exits the block. That's the same as in loguru:

```python hl_lines="10-12"
--8<-- "docs_src/advanced_threads_and_processes/tutorial006.py"
```

<div class="termy">

```console
$ python main.py

Got row 1 | {'source': 'orders.csv'}
Got row 2 | {'source': 'orders.csv'}
Done | {}
```

</div>

The `"Got ..."` lines are logged by the `for` loop, not by `read_rows()`, but they have the `source`, because the generator's block is still open while it is paused at `yield`. When the generator finishes, its block exits, and `"Done"` has no context.

If you don't want that, open the block around the code that uses the values, without a `yield` inside it.

/// tip | Performance

A plain `logger.info("msg")` inside a block costs the same as outside of it. The merged context is cached per thread, so logging inside a block stays on the fast Rust path.

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
* `contextualize()` is context-local: each thread and task sees only its own blocks.
* New threads start without the values, use `contextvars.copy_context().run()` to pass them. Tasks inherit them, generators share their caller's.
* With spawn or forkserver, configure logging in each process. With fork, the child inherits the handlers.
* Several processes can share a log file, rotation included.
* In forked children, `enqueue=True` sinks write synchronously.
* Logust supports free-threaded Python 3.14t, and keeps the GIL disabled.
