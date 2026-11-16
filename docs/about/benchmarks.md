# Benchmarks { #benchmarks }

The 0.6.0 candidate was compared directly with 0.5.0 using the same benchmark
and interpreter within each environment. Main file workloads took about
53–56% less time on macOS and 48–52% less time in Linux ARM64 Docker.

| Workload | macOS: 0.5.0 → candidate | Linux Docker: 0.5.0 → candidate | Time reduction: macOS / Linux |
|---|---:|---:|---:|
| Sync file, default format | 14.84 → **6.89 ms** | 17.47 → **8.80 ms** | 53.6% / 49.6% |
| Formatted messages | 16.28 → **7.55 ms** | 18.42 → **9.52 ms** | 53.6% / 48.3% |
| JSON | 15.60 → **7.39 ms** | 18.13 → **8.78 ms** | 52.6% / 51.6% |
| Bound context, sync | 14.74 → **6.89 ms** | 17.36 → **8.62 ms** | 53.3% / 50.3% |
| Async + complete() | 14.39 → **6.74 ms** | 18.03 → **9.06 ms** | 53.1% / 49.8% |
| Bound context, async + complete() | 14.76 → **6.91 ms** | 19.10 → **9.51 ms** | 53.2% / 50.2% |
| Async queue only | 14.67 → **6.53 ms** | 18.27 → **9.28 ms** | 55.5% / 49.2% |
| Callable sink, message only | 7.92 → **4.13 ms** | 8.31 → **4.15 ms** | 47.9% / 50.0% |
| Sync latency | 15.43 → **7.55 ms** | 18.32 → **9.73 ms** | 51.1% / 46.9% |
| Async queue latency | 16.30 → **8.32 ms** | 23.54 → **11.39 ms** | 48.9% / 51.6% |

Measured on 2026-11-16 using source-built release wheels, the same CPython
3.14.9 interpreter and Rust 1.96.0, on an Apple M4 Pro. Linux is native ARM64
inside an OrbStack Docker VM; logs use the container filesystem. Each version
ran in six independent processes, each with three timed suites after warmup;
the table compares the medians of the six process medians. Each throughput
case logs 10,000 messages, with output counts/content checked after timing.
The default file buffer is 8 KB in both versions. Flush completion is included
except in the explicitly labeled queue-only/async-queue-latency cases.

## Other performance changes

The additional 32-workload check found no case meeting the predeclared repeated
slowdown screen (a median slowdown of at least 5%, with at least five of six
pairs also at least 5% slower). This does **not** mean every case improved:
active exception output was **3.3% slower on macOS** (only 1/6 pairs faster),
and its Linux result was mixed (median 2.9% faster, only 2/6 pairs faster).
Long plain messages on macOS had one pair more than 5% slower despite an
improved overall median. All adverse samples are retained.

The 32 common-API cases include kwargs, module-level calls, small/large bind
values, JSON escaping, filters, patchers, callbacks, custom levels, Unicode,
long messages, markup, console writes, queues, rotation, opt/lazy/suppressed
calls, and active exceptions. New-only APIs and other configurations remain
outside this comparison. Regular-CPython performance results do not establish
free-threaded, Windows, x86-64 or bare-metal Linux performance.

## Reproduce and inspect

The repository contains the
[full tables and all raw results](https://github.com/yamaaaaaa31/logust/blob/main/benchmarks/results/0.6.0/README.md)
and the [comparison runner / pinned Linux tool image](https://github.com/yamaaaaaa31/logust/tree/main/benchmarks/release).
The throughput benchmark is benchmarks/bench_throughput.py. Build release
wheels for both revisions, install them in separate virtual environments with
the same Python, and alternate their execution outside the source checkouts.
Linux logs should remain on the container filesystem, not a host bind mount.

## Reading the results

- These are cumulative source-version comparisons, not a sum or product of earlier PR percentages.
- Flush is included in ordinary and async-complete cases. Queue-only and async queue latency exclude drain from the timer; cleanup still drains before validating output.
- Both Logust versions use the same default 8 KB file buffer. The previous cross-library snapshot used a different environment and is not mixed into these percentages. Loguru/logging normally write each line before returning; a per-line comparison requires buffering=1 and separate measurements.
- The previous PR #103 immediate-before enqueue regression remains an unresolved, separate comparison. No universal no-regression claim is made.
- Native serialize=True remains supported; the record migration described in the release notes concerns whole-record json.dumps() in filters, patchers and callbacks.
