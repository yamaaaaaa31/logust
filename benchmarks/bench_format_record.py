"""Light microbenchmark for Rust `format_record` path via Python (file handler).

Measures throughput when the format string includes caller, padded level, thread,
process, and elapsed — the hot path optimized in formatting allocation cleanup.

**Release build is required** (debug skews numbers). **Compare before vs after** the
change on the same machine: checkout baseline → `maturin develop --release` → run
this script and note logs/s → apply your change → rebuild release → run again.

```bash
maturin develop --release
uv run python benchmarks/bench_format_record.py
```
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

# Rich template → Rust FormatConfig::format_record with full LogRecord
FORMAT_RICH = (
    "{time} | {level:<8} | {name}:{function}:{line} | "
    "{thread} | {process} | {elapsed} | {message}"
)

N = 20_000


def main() -> None:
    from logust import Logger, LogLevel
    from logust._logust import PyLogger

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "bench.log"
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()
        logger.add(str(path), format=FORMAT_RICH, level="DEBUG")

        t0 = time.perf_counter()
        for _ in range(N):
            logger.debug("message")
        elapsed = time.perf_counter() - t0

    rate = N / elapsed
    print(f"format_record-style ({N} logs): {elapsed:.3f}s ({rate:,.0f} logs/s)")


if __name__ == "__main__":
    main()
