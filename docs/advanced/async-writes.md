# Async Writes { #async-writes }

By default, a file sink writes in the thread that logs the message. Writing to a file is fast most of the time, but disks and network file systems sometimes **stall**. And while the write waits, so does your code.

With `enqueue=True`, the logging call only puts the message in a **queue**, and a background thread writes it to the file.

## Enable async writes { #enable-async-writes }

Pass `enqueue=True` to `logger.add()`:

```python hl_lines="4 9"
--8<-- "docs_src/advanced_async_writes/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:06:10.061 | INFO     | __main__:<module>:7 - Processed batch 0
2026-10-06 12:06:10.061 | INFO     | __main__:<module>:7 - Processed batch 1
2026-10-06 12:06:10.061 | INFO     | __main__:<module>:7 - Processed batch 2
```

</div>

Everything else stays the same: the format, [rotation and retention](../tutorial/rotation-retention.md), [JSON](../tutorial/json-output.md)... `enqueue=True` only changes **who** writes to the file.

/// note

`enqueue` applies to **file** sinks. For console and callable sinks, it is ignored, and they keep writing in the calling thread.

///

## complete(): wait for the writes { #complete-wait-for-the-writes }

Did you notice the `logger.complete()` in the example?

With a queue, the message is not in the file yet when `logger.info()` returns. `logger.complete()` **waits** until every pending message has been written to the files, and flushes them.

You can see the difference:

```python hl_lines="13 15"
--8<-- "docs_src/advanced_async_writes/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

Before complete(): 0 lines
After complete(): 1 lines
```

</div>

Right after `logger.info()`, the file is still empty. After `logger.complete()`, the line is there. ✨

Call `logger.complete()`:

* Before you **read** your own log files, like in tests.
* Before your program **exits**, at shutdown. When Python exits normally, Logust writes what's left on its own (from an `atexit` handler). But an exit that skips cleanup, like `os._exit()` or a process killed by a signal, loses what is still in the queue: calling `complete()` during your shutdown code makes sure it's written before that point.
* Before you hand over a log file to someone else, for example before uploading it.

`logger.remove()` also writes the pending messages of the handlers it removes.

/// info

Sync file sinks (the default) don't need any of this: each logging call writes its line to the file before it returns, see [When it's written](../tutorial/file-output.md#make-sure-its-written). `logger.complete()` is harmless for them, so you can call it at shutdown whatever your sinks are. The same advice applies to sync sinks with `buffering=N`, which keep lines in memory until their buffer is full.

///

## How the queue works { #how-the-queue-works }

A few details that are good to know:

* Each `enqueue=True` sink has its own background **writer thread**.
* The writer batches lines, and every line reaches the file at most **100 ms** after it was logged, even when messages keep coming. So `tail -f app.log` keeps up without `complete()`.
* That batching is the trade-off: if the process is killed, the messages of the last ~100 ms, and anything still in the queue, are lost. Sync sinks don't have that window.
* The queue holds up to **10,000** messages. If it's full, because the disk can't keep up, the logging call **waits** for room instead of dropping messages.
* If the writer fails to write (disk full, permissions...), the error is printed to stderr, whatever the [`catch=` setting](sink-errors.md) is. With a queue, there's no logging call left to raise it from.

## Sync or async? { #sync-or-async }

Logust's sync writes are already fast: the formatting and writing happen in Rust, and most of the time goes to the one `write()` system call per message that keeps each line safe. `enqueue=True` batches those system calls in a background thread, so it's faster still, but above all it's about **not blocking**.

| | `enqueue=False` (default) | `enqueue=True` |
|-|---------------------------|----------------|
| Who writes | The calling thread | A background thread |
| A slow disk... | ...slows down the logging call | ...is absorbed by the queue |
| Errors | Can be [reported or raised](sink-errors.md) by the logging call | Printed to stderr by the writer thread |
| Process killed (`SIGTERM`, `os._exit()`, crash) | Every logged line is in the file (up to `N` bytes lost with `buffering=N`) | The last ~100 ms of messages can be lost |
| Good for | Most apps, scripts, CLIs | Web servers, high-throughput services, slow or network storage |

Here's the time spent in the **main thread** for 10,000 messages, in one run of the benchmark suite ([`benchmarks/bench_throughput.py`](https://github.com/yamaaaaaa31/logust/tree/main/benchmarks)):

| Library | Sync | Async |
|---------|------|-------|
| loguru | 92.72 ms | 378.00 ms |
| logust | 26.17 ms | 8.76 ms |

In that run, loguru's `enqueue=True` path was slower than its sync path, while Logust's async path took about a third of its sync time. Your numbers will depend on your machine and disk, see [Benchmarks](../about/benchmarks.md) to reproduce them.

/// tip

Use `enqueue=True` when a **stalled disk must never stall your requests**. For a script or a CLI, the default is simpler, and errors surface where they happen. If you only want fewer system calls, `buffering=65536` batches the writes in the calling thread, see [Faster: buffering or a background thread](../tutorial/file-output.md#buffering). With `enqueue=True`, `buffering` is ignored.

///

## Forked processes { #forked-processes }

A process created with `fork()` never starts a writer thread: `enqueue=True` sinks inherited from the parent write **synchronously** in the child. On macOS, sinks added in the child do too. See [Threads and Processes](threads-and-processes.md#fork-caveats) for the details.

## Recap { #recap }

* `logger.add("app.log", enqueue=True)` writes in a background thread.
* `logger.complete()` waits until all pending messages are written. Call it at shutdown and before reading your logs. Normal exits drain the queue on their own, killed processes don't.
* Messages reach the file within ~100 ms. Sync sinks write each line before the call returns.
* The queue holds 10,000 messages, and waits instead of dropping when it's full.
* `enqueue=True` is for not blocking and batching writes, Logust's sync writes are already fast.
