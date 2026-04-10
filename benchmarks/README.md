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

# Pytest wrapper (same scenarios, 10 cases)
pytest benchmarks/bench_throughput.py -v

# Other scripts
python benchmarks/bench_filter_mixed.py
```

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

See [Comparison](../docs/comparison.md) for latest benchmark results.
