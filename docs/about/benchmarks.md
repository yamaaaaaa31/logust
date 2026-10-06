# Benchmarks { #benchmarks }

How fast is Logust, compared to the standard `logging` module and loguru? Here are the numbers. 🚀

They come from one recent run of the benchmark suite in the repository (`benchmarks/bench_throughput.py`), with a **release** build, on the maintainer's machine. Your numbers will be different, but the proportions should be similar. You can [run them yourself](#run-the-benchmarks).

## What is measured { #what-is-measured }

Each scenario logs **10,000 messages** with each library and measures the total time, including the final flush (`complete()`), except in the "no wait" and latency scenarios. Lower is better.

The libraries are configured to write the same kind of line to a file: time, level, `module:function:line` and the message. The console is turned off for all of them.

## Throughput { #throughput }

| Scenario | logging | loguru | logust |
|----------|---------|--------|--------|
| File write (sync) | 963.57 ms | 2676.74 ms | **15.93 ms** |
| Formatted messages | 966.38 ms | 2710.67 ms | **15.65 ms** |
| JSON serialize | N/A | 2717.99 ms | **14.91 ms** |
| With context (sync) | N/A | 2600.08 ms | **14.29 ms** |

In this run, Logust stayed in the mid-teens of milliseconds for sync file writes, formatted messages, JSON serialization and bound context.

`N/A`: the standard `logging` module has no built-in JSON output or context binding, so those scenarios are not measured for it.

## Async writes { #async-writes }

With `enqueue=True`, the file writes happen in a background thread. See [Async Writes](../advanced/async-writes.md).

| Scenario | loguru | logust |
|----------|--------|--------|
| File write (async + complete) | 3019.49 ms | **16.50 ms** |
| With context (async + complete) | 3062.94 ms | **16.99 ms** |
| Async non-blocking (no wait) | 3158.39 ms | **16.18 ms** |

## Sync vs async latency { #sync-vs-async-latency }

This one measures the time spent in the **main thread** only. That's the real benefit of async writes: your code doesn't wait for the disk.

| Library | Sync | Async |
|---------|------|-------|
| loguru | 2704.37 ms | 3225.03 ms |
| logust | 15.01 ms | 17.20 ms |

In this run, loguru's `enqueue=True` path was slower than its sync path, while Logust's async path stayed close to its sync latency.

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
