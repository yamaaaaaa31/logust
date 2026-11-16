# Release comparison

`compare.py` checks 32 workloads supported by both 0.5.0 and 0.6.0: ordinary,
formatted and module-level logging; small and large bound context; JSON,
callables, filters, patchers and callbacks; custom levels; Unicode, long text,
markup, console, queues and rotation; enabled/lazy/suppressed `opt()` and
exception logging.

Build both revisions as **release wheels**, install them in separate virtual
environments using the same interpreter, and run outside either checkout:

```bash
python /path/to/benchmarks/release/compare.py \
  /path/to/baseline/env/bin/python \
  /path/to/candidate/env/bin/python \
  /path/to/broad-results.json --processes 6 --calls 20000
```

The default is six independent processes per version, reversing their order in
each pair. Each process warms up each case, then records three timed samples;
the headline compares the medians of the six process medians. Samples within
one process are nested, not independent replications. The `bound_large_extra`,
`json_bound`, `long_message` and `late_markup` cases use at most 2,000 calls per
sample, and exception cases at most 500.
`complete()` is included in every timed sample. Output checks run afterwards.

The JSON includes every process/sample, native extension hash, output counts,
semantic fingerprints, and all paired changes, including adverse results. A
`repeated_slowdown` means the candidate median is at least 5% slower and at
least five of six process pairs are at least 5% slower. This descriptive rule
was chosen before the 0.6.0 broad measurements; it is not a significance test.
Inspect small/mixed changes too. Passing this screen does not establish that
every API, configuration or platform is free from regressions.

Semantic validation checks messages, counts, JSON severity and bound values,
ANSI markup, and whether suppressed lazy callbacks stay uncalled. Record
wrapper types and traceback presentation intentionally changed in 0.6.0;
their byte-for-byte equivalence is not asserted. The 0.6.0 test suite checks
those contracts separately. This harness stays within the shared API, so new
features such as positional logger arguments and `buffering=1` need separate
functional checks rather than a fabricated 0.5.0 timing.

## Linux tool image

```bash
docker build --platform linux/arm64 -t logust-release-check:0.6.0 \
  -f benchmarks/release/Dockerfile benchmarks/release
```

The Dockerfile pins the Python base image and Rust toolchain. Build the wheels
and run the same comparison inside that image. Keep source, installed wheels
and temporary log files on the container's native filesystem, not a host bind
mount; only export results. Record the actual package freeze and image ID, as
test-tool dependencies and Debian packages are resolved when the image is built.
Native ARM64 Linux in Docker on an Apple Silicon host is a VM measurement,
not evidence about x86-64, bare-metal Linux or free-threaded performance.

See [the 0.6.0 evidence](../results/0.6.0/README.md) for environments, complete
throughput/broad results, limitations and validation outcomes.
