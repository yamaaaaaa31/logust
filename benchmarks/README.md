# Benchmarks

Performance benchmarks comparing logust with Python logging and loguru.

## Release build (required for meaningful Rust numbers)

The extension must be built in **release** mode. A debug build skews throughput and is not comparable to published wheels.

```bash
maturin develop --release
```

(`cargo build --release` alone is not enough unless you reinstall the resulting artifact the same way your environment loads `_logust`.)

## Running Benchmarks

Default `pytest` only discovers `tests/` (see `pyproject.toml`). Run benchmarks explicitly:

```bash
# After: maturin develop --release
# Full suite (prints comparison tables)
uv pip install loguru   # optional dependency for loguru rows
python benchmarks/bench_throughput.py

# Pytest wrapper (same scenarios, 9 cases)
pytest benchmarks/bench_throughput.py -v

# Other scripts
python benchmarks/bench_filter_mixed.py

# format_record hot path (rich template: thread, process, elapsed, padded level)
python benchmarks/bench_format_record.py
```

### `bench_format_record.py` — before/after

Use a **release** build (`maturin develop --release` above). For allocation/formatting work, **compare the printed throughput on the baseline commit vs after your change** on the same machine (same `N`, quiet system). A single run without a baseline only tells you absolute speed, not regression or improvement.

## Requirements

```bash
uv sync                           # dev / test deps from the project
uv pip install loguru             # optional: enables loguru comparison rows
```

## Callable sink (formatted) vs raw callback

Throughput comparisons for the **lightweight formatted callable sink** path are meaningful only when:

- `filter=None`, `serialize=False`
- No **raw** `add_callback` registered (raw callbacks force full record collection)
- Callable sink uses `logger.add(lambda msg: ..., format="...")` only

Mixing raw callbacks or filters changes what gets measured.

## Results

See [Benchmarks](../docs/about/benchmarks.md) for latest benchmark results.

## Collection and context regression benchmark

`bench_review_fixes.py` exercises ordinary file, JSON, callable and console output,
mixed-severity sinks, bound context, and suppressed exception logging. Run the
same script from outside the checkout using baseline and candidate interpreters
with release wheels installed. It verifies the imported package is installed,
checks output, and prints per-case timing and output fingerprints as JSON.
Alternate baseline/candidate runs and compare medians; keep the compiler,
dependencies, call counts and script identical. Do not use debug builds.

```bash
cd /tmp
/path/to/baseline/bin/python /path/to/logust/benchmarks/bench_review_fixes.py --calls 30000
/path/to/candidate/bin/python /path/to/logust/benchmarks/bench_review_fixes.py --calls 30000
```
