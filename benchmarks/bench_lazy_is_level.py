"""Microbenchmark for disabled lazy logs (is_level_enabled read path).

No console/file output: logger.disable() then many handlers/callbacks, opt(lazy=True).debug.

Run:
    uv run python benchmarks/bench_lazy_is_level.py
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

N = 50_000
MANY = 256


def _bench(name: str, fn) -> float:
    start = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - start
    print(f"{name}: {elapsed * 1000:.2f} ms ({N} opt(lazy=True).debug calls)")
    return elapsed


def main() -> None:
    from logust import Logger, LogLevel
    from logust._logust import PyLogger

    # Callback-only, no I/O (codex/doc/performance/02)
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    for _ in range(MANY):
        logger.add_callback(lambda _r: None, level="ERROR")

    opt = logger.opt(lazy=True)

    def run_lazy_debug() -> None:
        for i in range(N):
            opt.debug("x{}", lambda: i)

    _bench(f"disabled + {MANY} ERROR callbacks, lazy debug (below threshold)", run_lazy_debug)

    # Many file handlers, still disabled console — records below handler level skip dispatch
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir)
        inner2 = PyLogger(LogLevel.Trace)
        logger2 = Logger(inner2)
        logger2.disable()
        for j in range(MANY):
            logger2.add(
                str(p / f"h{j}.log"),
                level=LogLevel.Error,
                format="{message}",
                enqueue=False,
            )

        opt2 = logger2.opt(lazy=True)

        def run_many_handlers() -> None:
            for i in range(N):
                opt2.debug("x{}", lambda: i)

        _bench(
            f"disabled console + {MANY} ERROR file handlers, lazy debug (below threshold)",
            run_many_handlers,
        )
        logger2.complete()


if __name__ == "__main__":
    main()
