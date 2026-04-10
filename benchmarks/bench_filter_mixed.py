"""Mixed-handler filter microbenchmark (format=\"{message}\" on INFO path).

Compares three configurations from codex/doc/performance/01-filter-fast-path.md:

1. Single INFO file handler (baseline).
2. INFO file + ERROR file with Python filter (should approach (1) after filter fast path).
3. INFO file + INFO file with filter (filter always eligible; control / regression).

Run:
    uv run python benchmarks/bench_filter_mixed.py
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

N = 20_000


def _bench(name: str, fn) -> float:
    start = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - start
    print(f"{name}: {elapsed * 1000:.2f} ms ({N} logs)")
    return elapsed


def main() -> None:
    from logust import Logger, LogLevel
    from logust._logust import PyLogger

    results: dict[str, float] = {}

    # Case 1: INFO only
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()
        logger.add(str(p / "info.log"), level=LogLevel.Info, format="{message}", enqueue=False)

        def run1() -> None:
            for i in range(N):
                logger.info(f"m{i}")

        results["1_info_only"] = _bench("1 INFO file, format={message}", run1)
        logger.complete()

    # Case 2: INFO + ERROR filtered
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()
        logger.add(str(p / "info.log"), level=LogLevel.Info, format="{message}", enqueue=False)
        logger.add(
            str(p / "err.log"),
            level=LogLevel.Error,
            format="{message}",
            filter=lambda _r: True,
            enqueue=False,
        )

        def run2() -> None:
            for i in range(N):
                logger.info(f"m{i}")

        results["2_info_plus_error_filtered"] = _bench(
            "2 INFO + ERROR filtered", run2
        )
        logger.complete()

    # Case 3: INFO + INFO filtered
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()
        logger.add(str(p / "a.log"), level=LogLevel.Info, format="{message}", enqueue=False)
        logger.add(
            str(p / "b.log"),
            level=LogLevel.Info,
            format="{message}",
            filter=lambda _r: True,
            enqueue=False,
        )

        def run3() -> None:
            for i in range(N):
                logger.info(f"m{i}")

        results["3_info_plus_info_filtered"] = _bench("3 INFO + INFO filtered", run3)
        logger.complete()

    gap = results["2_info_plus_error_filtered"] / results["1_info_only"]
    print(f"Ratio (2)/(1): {gap:.2f}x")


if __name__ == "__main__":
    main()
