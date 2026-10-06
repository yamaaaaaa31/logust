# Benchmarks { #benchmarks }

How fast is Logust, compared to the standard `logging` module and loguru? Here are the numbers. 🚀

They are the medians of three runs of the benchmark suite in the repository (`benchmarks/bench_throughput.py`), with a **release** build, on an Apple Silicon Mac with CPython 3.14. Your numbers will be different, but the proportions should be similar. You can [run them yourself](#run-the-benchmarks).

## What is measured { #what-is-measured }

Each scenario logs **10,000 messages** with each library and measures the total time, including the final flush (`complete()`), except in the "no wait" and latency scenarios. Lower is better.

The libraries are configured to write the same kind of line to a file: time, level, `module:function:line` and the message. The console is turned off for all of them.

## Throughput { #throughput }

| Scenario | logging | loguru | logust |
|----------|---------|--------|--------|
| File write (sync) | 81.58 ms | 90.61 ms | **8.32 ms** |
| File write (sync, one write per line) | 83.42 ms | 89.44 ms | **29.75 ms** |
| Formatted messages | 82.34 ms | 106.49 ms | **8.80 ms** |
| JSON serialize | N/A | 188.64 ms | **9.12 ms** |
| With context (sync) | N/A | 88.73 ms | **7.12 ms** |

Logust buffers file writes by default (8 KB), while loguru and `logging` write each line before the logging call returns. The "one write per line" row compares like with like: Logust with `buffering=1`, so that every logged line survives a kill. The `write()` system call per message is then most of Logust's time. See [When it's written](../tutorial/file-output.md#make-sure-its-written).

`N/A`: the standard `logging` module has no built-in JSON output or context binding, so those scenarios are not measured for it.

## Async writes { #async-writes }

With `enqueue=True`, the file writes happen in a background thread. See [Async Writes](../advanced/async-writes.md).

| Scenario | loguru | logust |
|----------|--------|--------|
| File write (async + complete) | 437.38 ms | **7.09 ms** |
| With context (async + complete) | 402.73 ms | **7.15 ms** |
| Async non-blocking (no wait) | 425.22 ms | **6.88 ms** |

## Sync vs async latency { #sync-vs-async-latency }

This one measures the time spent in the **main thread** only. That's the real benefit of async writes: your code doesn't wait for the disk.

| Library | Sync | Async |
|---------|------|-------|
| loguru | 86.60 ms | 370.86 ms |
| logust | 8.25 ms | 9.06 ms |

In these runs, loguru's `enqueue=True` path was slower than its sync path, while Logust's async path stayed close to its sync latency.

## Run the benchmarks { #run-the-benchmarks }

You can reproduce these numbers from a clone of the repository.

/// warning

Build the extension in **release** mode first. A debug build is much slower, and its numbers are not comparable to the published wheels.

///

<div class="termy">

```console
// Install the development dependencies
$ uv sync

---> 100%

// Build the Rust extension in release mode
$ maturin develop --release

---> 100%

// Optional: install loguru to get its rows too
$ uv pip install loguru

---> 100%

// Run the full suite, it prints the comparison tables
$ python benchmarks/bench_throughput.py
```

</div>

The same scenarios are available as a pytest suite, and there are a few more focused scripts:

<div class="termy">

```console
$ pytest benchmarks/bench_throughput.py -v

// Filters on a mix of handlers
$ python benchmarks/bench_filter_mixed.py

// The format_record hot path (thread, process, elapsed, padded level)
$ python benchmarks/bench_format_record.py
```

</div>

/// tip

To check if a change makes Logust faster or slower, compare the numbers on the **baseline** commit and **after** your change, on the same machine, with the same `N`, and with the system as quiet as possible. One run on its own only tells you the absolute speed.

///

You can find more details in <a href="https://github.com/yamaaaaaa31/logust/blob/main/benchmarks/README.md" class="external-link" target="_blank">`benchmarks/README.md`</a>.
