---
title: Logust
description: Fast, Rust-powered Python logging library with loguru-style API, JSON logging, and file rotation.
---

<p align="center">
  <img src="assets/logo.svg" alt="Logust" width="200">
</p>

<p align="center">
  <strong>Fast, Rust-powered Python logging inspired by loguru</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/logust/"><img src="https://badge.fury.io/py/logust.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/logust/"><img src="https://img.shields.io/pypi/pyversions/logust.svg" alt="Python Versions"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

---

!!! success "14x faster than loguru, 4x faster than logging"

## Installation

```bash
pip install logust
```

## Quick Start

```python
import logust

logust.info("Hello, Logust!")
logust.debug("Debug message")
logust.warning("Warning message")
logust.error("Error message")
```

```text
2025-12-24 15:52:42.199 | INFO     | Hello, Logust!
2025-12-24 15:52:42.199 | DEBUG    | Debug message
2025-12-24 15:52:42.199 | WARNING  | Warning message
2025-12-24 15:52:42.199 | ERROR    | Error message
```

## Key Features

- **Blazing Fast** - Rust-powered core delivers 5-24x faster performance
- **Beautiful by Default** - Colored output with zero configuration
- **Simple API** - loguru-compatible interface for easy migration
- **File Management** - Size/time-based rotation, retention policies, gzip compression
- **JSON Support** - Built-in serialization for structured logging
- **Context Binding** - Attach metadata to log records with `bind()`
- **Exception Handling** - Automatic traceback capture with `catch()` decorator

## From Hello to Production

=== "Hello"
    ```python
    import logust

    logust.info("Hello, Logust!")
    logust.warning("Heads up")
    ```

=== "Production"
    ```python
    from logust import logger

    logger.add(
        "app.log",
        level="INFO",
        rotation="500 MB",
        retention="30 days",
        compression=True,
        serialize=True,
        enqueue=True,
    )
    ```

## Next Steps

- [Installation](getting-started/installation.md) - Get started with Logust
- [Quick Start](getting-started/quick-start.md) - Learn the basics
- [File Output](guide/file-output.md) - Rotation, retention, compression
- [Formatting](guide/formatting.md) - Custom formats and JSON
- [Comparison](comparison.md) - Logust vs loguru vs logging
