# Benchmarks

Performance benchmarks comparing logust with Python logging and loguru.

## Running Benchmarks

```bash
# Run all benchmarks
uv run python -m pytest benchmarks/ -v

# Run specific benchmark
uv run python benchmarks/bench_throughput.py
```

## Requirements

Install benchmark dependencies:

```bash
uv sync --group dev
```

## Results

See [Comparison](../docs/comparison.md) for latest benchmark results.
