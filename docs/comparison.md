# Comparison

## At a glance

### Logust

- Rust core and high throughput
- Loguru-style API
- Rotation, retention, JSON, async writes

### Loguru

- Rich sink options
- More built-in record fields
- Long-established ecosystem

### logging

- Standard library
- Very configurable but verbose
- Slower by default

## Benchmarks (10,000 messages)

Results below are from one recent release-build run of the included benchmark suite (`benchmarks/bench_throughput.py`) on the current maintainer machine. Use `benchmarks/README.md` to reproduce them in your environment.

### Summary

Logust stayed in the mid-teens millisecond range for sync file writes, formatted messages, JSON serialization, bound context, and async file writes in this run.

### Throughput

| Scenario | logging | loguru | logust |
|----------|---------|--------|--------|
| File write (sync) | 963.57 ms | 2676.74 ms | **15.93 ms** |
| Formatted messages | 966.38 ms | 2710.67 ms | **15.65 ms** |
| JSON serialize | N/A | 2717.99 ms | **14.91 ms** |
| With context (sync) | N/A | 2600.08 ms | **14.29 ms** |

### Async writes

| Scenario | loguru | logust |
|----------|--------|--------|
| File write (async + complete) | 3019.49 ms | **16.50 ms** |
| With context (async + complete) | 3062.94 ms | **16.99 ms** |
| Async non-blocking (no wait) | 3158.39 ms | **16.18 ms** |

### Sync vs Async latency

This measures main thread time only - the true benefit of async is not blocking I/O.

| Library | Sync | Async |
|---------|------|-------|
| loguru | 2704.37 ms | 3225.03 ms |
| logust | 15.01 ms | 17.20 ms |

In this run, `loguru`'s `enqueue=True` path remained far slower than its sync path, while `logust`'s async path stayed close to its sync latency.

## Feature comparison

| Feature | logust | loguru |
|---------|--------|--------|
| Colored output | Yes | Yes |
| File rotation | Yes | Yes |
| File retention | Yes | Yes |
| Compression | Yes | Yes |
| JSON output | Yes | Yes |
| Context binding | Yes | Yes |
| Custom levels | Yes | Yes |
| Exception catching | Yes | Yes |
| Lazy evaluation | Yes | Yes |
| Async writes | Yes | Yes |
| Callable sinks | Yes | Yes |
| Stack info (module, function, line) | Yes | Yes |
| Process/thread info | Yes | Yes |

## API differences

Most loguru code works with logust with minimal changes:

```python
# loguru
from loguru import logger
logger.add("app.log", rotation="500 MB")
logger.info("Hello")

# logust (same API for common usage)
from logust import logger
logger.add("app.log", rotation="500 MB")
logger.info("Hello")
```

## When to choose logust

- Performance and throughput are critical
- You want a loguru-style API with fewer dependencies
- You need rotation, retention, JSON, callable sinks, and async writes

## When to choose loguru

- You need full loguru compatibility for advanced features
- You need richer built-in record fields or sink options

## Logust vs standard logging

### Advantages of logust

1. Zero configuration with readable defaults
2. Better performance out of the box
3. Simpler API with fewer moving parts
4. Built-in rotation, retention, and colors

### Migration example

```python
# Standard logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
logger.info("Hello")

# Logust (simpler)
from logust import logger
logger.add("app.log")
logger.info("Hello")
```
