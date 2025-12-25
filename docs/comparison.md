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

Results are from the included benchmark suite (`benchmarks/bench_throughput.py`).

### Summary

```
logust vs loguru:  16.8x faster on average
logust vs logging:  4.6x faster on average
```

Logust includes rich caller information (module, function, line) in every log message while maintaining excellent performance.

### Throughput

| Scenario | logging | loguru | logust | vs loguru |
|----------|---------|--------|--------|-----------|
| File write (sync) | 57.18 ms | 65.57 ms | **10.84 ms** | 6.1x faster |
| Formatted messages | 55.99 ms | 65.81 ms | **11.62 ms** | 5.7x faster |
| JSON serialize | N/A | 134.12 ms | **10.96 ms** | 12.2x faster |
| Context binding | N/A | 64.12 ms | **10.35 ms** | 6.2x faster |

### Async writes

| Scenario | loguru | logust | vs loguru |
|----------|--------|--------|-----------|
| File write (async) | 326.27 ms | **10.23 ms** | 31.9x faster |

### Sync vs Async latency

This measures main thread time only - the true benefit of async is not blocking I/O.

| Library | Sync | Async | Effect |
|---------|------|-------|--------|
| loguru | 70.44 ms | 299.61 ms | **4.3x slower** |
| logust | 10.64 ms | 11.57 ms | **No overhead** |

**Key finding**: loguru's `enqueue=True` adds significant overhead due to Python's `queue.Queue`. Logust uses Rust's lock-free crossbeam channels, maintaining speed while offloading I/O.

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
| Callable sinks | No | Yes |
| Stack info (module, function, line) | Yes | Yes |
| Process/thread info | No | Yes |

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
- You need rotation, retention, JSON, and async writes

## When to choose loguru

- You need callable sinks or richer built-in record fields
- You need full loguru compatibility for advanced features

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
