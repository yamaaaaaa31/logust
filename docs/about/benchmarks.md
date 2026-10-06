# Benchmarks { #benchmarks }

How fast is Logust, compared to the standard `logging` module and loguru? Here are the numbers. 🚀

They come from one recent run of the benchmark suite in the repository (`benchmarks/bench_throughput.py`), with a **release** build, on an Apple Silicon Mac with CPython 3.14. Your numbers will be different, but the proportions should be similar. You can [run them yourself](#run-the-benchmarks).

## What is measured { #what-is-measured }

Each scenario logs **10,000 messages** with each library and measures the total time, including the final flush (`complete()`), except in the "no wait" and latency scenarios. Lower is better.

The libraries are configured to write the same kind of line to a file: time, level, `module:function:line` and the message. The console is turned off for all of them.

## Throughput { #throughput }

| Scenario | logging | loguru | logust |
|----------|---------|--------|--------|
| File write (sync) | 69.68 ms | 81.39 ms | **22.86 ms** |
| File write (sync, `buffering=65536`) | N/A | 53.54 ms | **7.55 ms** |
| Formatted messages | 70.12 ms | 85.13 ms | **24.22 ms** |
| JSON serialize | N/A | 167.82 ms | **25.43 ms** |
| With context (sync) | N/A | 90.16 ms | **24.04 ms** |

In the sync scenarios, all three libraries write each line to the file before the logging call returns (one `write()` system call per message), so a logged line survives a crash or a kill. That system call is most of Logust's time here: the formatting itself happens in Rust. The `buffering=65536` row batches the writes in a 64 KiB buffer instead (loguru passes `buffering` to `open()`; `logging.FileHandler` has no such option). See also the async scenarios below.

`N/A`: the standard `logging` module has no built-in JSON output, context binding or write buffering for files, so those scenarios are not measured for it.

## Async writes { #async-writes }

With `enqueue=True`, the file writes happen in a background thread. See [Async Writes](../advanced/async-writes.md).

| Scenario | loguru | logust |
|----------|--------|--------|
| File write (async + complete) | 448.00 ms | **6.87 ms** |
| With context (async + complete) | 365.72 ms | **6.90 ms** |
| Async non-blocking (no wait) | 335.22 ms | **6.64 ms** |

## Sync vs async latency { #sync-vs-async-latency }

This one measures the time spent in the **main thread** only. That's the real benefit of async writes: your code doesn't wait for the disk.

| Library | Sync | Async |
|---------|------|-------|
| loguru | 92.72 ms | 378.00 ms |
| logust | 26.17 ms | 8.76 ms |

In this run, loguru's `enqueue=True` path was slower than its sync path, while Logust's async path took about a third of its sync latency: the background thread writes many lines per system call.

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
