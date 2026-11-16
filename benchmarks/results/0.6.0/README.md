# 0.6.0 release-candidate performance evidence

Measured on 2026-11-16 using source-built release wheels, the same CPython
3.14.9 interpreter and Rust 1.96.0, on an Apple M4 Pro. Linux is native ARM64
inside an OrbStack Docker VM; logs use the container filesystem. Each version
ran in six independent processes, each with three timed suites after warmup;
the table compares the medians of the six process medians. Each throughput
case logs 10,000 messages, with output counts/content checked after timing.
The default file buffer is 8 KB in both versions. Flush completion is included
except in the explicitly labeled queue-only/async-queue-latency cases.

## Throughput vs 0.5.0

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

Time reduction is (baseline − candidate) / baseline; throughput multiplier is
baseline / candidate. Queue-only timings exclude final drain, which still runs
before output verification. They are separate workloads from async + complete().

## Additional 32 workloads

Negative elapsed change is faster. Each number compares medians of six
independent process medians, with all six paired directions shown separately.

The additional 32-workload check found no case meeting the predeclared repeated
slowdown screen (a median slowdown of at least 5%, with at least five of six
pairs also at least 5% slower). This does **not** mean every case improved:
active exception output was **3.3% slower on macOS** (only 1/6 pairs faster),
and its Linux result was mixed (median 2.9% faster, only 2/6 pairs faster).
Long plain messages on macOS had one pair more than 5% slower despite an
improved overall median. All adverse samples are retained.

| Workload | macOS elapsed change | Faster pairs | Linux elapsed change | Faster pairs |
|---|---:|---:|---:|---:|
| message | -53.22% | 6/6 | -49.95% | 6/6 |
| default | -62.94% | 6/6 | -59.12% | 6/6 |
| kwargs | -35.57% | 6/6 | -31.26% | 6/6 |
| module | -67.48% | 6/6 | -64.25% | 6/6 |
| bound_small | -53.72% | 6/6 | -50.43% | 6/6 |
| bound_large | -51.53% | 6/6 | -51.70% | 6/6 |
| bound_large_extra | -69.34% | 6/6 | -66.89% | 6/6 |
| json | -63.49% | 6/6 | -59.96% | 6/6 |
| json_escaped | -61.03% | 6/6 | -58.91% | 6/6 |
| json_bound | -61.65% | 6/6 | -57.51% | 6/6 |
| callable | -54.41% | 6/6 | -53.64% | 6/6 |
| callable_json | -22.81% | 6/6 | -19.92% | 6/6 |
| filter | -33.53% | 6/6 | -29.58% | 6/6 |
| patcher | -12.29% | 6/6 | -11.55% | 5/6 |
| callback | -32.39% | 6/6 | -27.50% | 6/6 |
| custom_level | -35.12% | 6/6 | -30.23% | 6/6 |
| unicode | -52.14% | 6/6 | -50.31% | 6/6 |
| long_message | -7.41% | 5/6 | -15.52% | 6/6 |
| markup_color | -41.74% | 6/6 | -48.32% | 6/6 |
| markup_strip | -42.29% | 6/6 | -47.68% | 6/6 |
| late_markup | -45.56% | 6/6 | -59.38% | 6/6 |
| console | -47.67% | 6/6 | -49.14% | 6/6 |
| enqueue | -37.74% | 6/6 | -43.90% | 6/6 |
| rotation | -10.94% | 6/6 | -21.14% | 6/6 |
| opt_enabled | -34.25% | 6/6 | -36.40% | 6/6 |
| opt_args | -7.33% | 6/6 | -12.29% | 6/6 |
| opt_lazy | -27.19% | 6/6 | -26.59% | 6/6 |
| suppressed | -26.44% | 6/6 | -25.49% | 6/6 |
| suppressed_lazy | -75.85% | 6/6 | -76.00% | 6/6 |
| suppressed_exception | -99.91% | 6/6 | -99.91% | 6/6 |
| suppressed_opt_exception | -99.91% | 6/6 | -99.90% | 6/6 |
| active_exception | +3.32% | 1/6 | -2.88% | 2/6 |

## Protocol and scope

- Baseline: v0.5.0, commit 6d7962129c55d8c98eb9b77cce0b7ad0c0f7e573.
- Candidate implementation: commit 936c7821ad07c8c95d0e20200615215ce56c1c92. The macOS study precedes the version bump; Linux adds 0.6.0 package metadata. This preparation PR changes no production performance code.
- macOS 27.2.1; Linux kernel 7.2.12-orbstack-00394-gbecdd6130068 / Debian bookworm container; aarch64; regular GIL-enabled CPython 3.14.9. Both wheels were built afresh using maturin 1.15.0 and Rust 1.96.0. This compares same-environment source builds, not the previously uploaded PyPI wheel.
- Common non-PyO3 Rust dependencies resolve to matching versions. The package graphs differ in PyO3 0.29.3 → 0.30.1 and the added bzip2 dependencies. The macOS manifests retain both graphs; the Linux study reused the corresponding lockfiles, changing only the candidate root package version.
- Original throughput functions, N=10,000, library order, timers and complete() placement are unchanged. One suite warms up each fresh process; three suites are nested within it. Process order is old/new/new/old, new/old/old/new, old/new/new/old. Every file's message count/order/content is checked after timing; JSON message/level and a separate callable/bind probe are checked too. Full timestamp/caller/record-field equality is not claimed.
- Additional workloads use the committed compare.py, 6 process pairs in alternating order, 100 warmup calls and 3 timed samples per case. Ordinary cases use 20,000 calls/sample; bound_large_extra, json_bound, long_message and late_markup use at most 2,000; exception cases at most 500. The test runs inside an existing exception context; raising the exception is outside timing. Output checks run afterwards. Tracebacks are checked for the message and exception, not byte equality; record-type/API changes are intentionally outside the normalized message fingerprint.
- All timing samples and paired signs are retained. No outlier removal, A/A adjustment, cross-platform pooling, or multiplication of old optimization percentages. External host load and scheduler noise are uncontrolled. The slowdown screen was fixed before inspecting these broad results and is descriptive, not a significance test.
- No results here establish all-conditions no-regression, free-threaded/Windows/x86-64 performance, fsync durability, or bare-metal Linux behavior. New-only APIs and unsupported 0.5.0 options are not benchmark comparisons.
- PR #103's immediate-before enqueue_text comparison was +2.649%, with only 1/4 processes faster. Its cause/resolution remains unconfirmed. A cumulative 0.5.0 improvement does not resolve that separate comparison.
- The existing default-buffering difference from loguru/logging remains: this release comparison uses Logust's same 8 KB default in both revisions. Do not use it to claim a like-for-like per-line durability speedup over other libraries.

## Validation

Linux ARM64 Docker built and installed the 0.6.0 wheel and verified both
logust.__version__ and installed distribution metadata. Full installed-wheel
Python tests: **1,342 passed, 2 skipped**; Rust tests: **127 passed**. The Python
run had one FastAPI/Starlette deprecation warning. Skipped tests are counted
separately from passes. These functional checks are distinct from performance
measurements.

## Files

- [macOS throughput](macos-throughput.json) / [Linux throughput](linux-throughput.json): environments, source/wheel/native hashes, process medians, all nested suites, library controls and output checks.
- [macOS broad cases](macos-broad.json) / [Linux broad cases](linux-broad.json): all 32 cases, every process/sample, paired signs, output counts and semantic hashes.
- [Validation metadata](validation.json) / [Linux test dependency freeze](linux-test-dependencies.txt).
- [Comparison runner and Linux Dockerfile](../../release/README.md). Raw process rows are compacted for file size, with no data removed.
