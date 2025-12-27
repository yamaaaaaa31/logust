"""Benchmark throughput comparison: logust vs logging vs loguru.

Run with:
    uv run python -m pytest benchmarks/bench_throughput.py -v

Or directly:
    uv run python benchmarks/bench_throughput.py
"""

from __future__ import annotations

import io
import logging
import tempfile
import time
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any

# Number of log messages per benchmark
N = 10_000


def setup_python_logging(log_file: Path | None = None) -> logging.Logger:
    """Set up Python standard logging."""
    py_logger = logging.getLogger("benchmark")
    py_logger.setLevel(logging.DEBUG)
    py_logger.handlers.clear()

    if log_file:
        handler = logging.FileHandler(str(log_file))
    else:
        handler = logging.NullHandler()

    handler.setLevel(logging.DEBUG)
    # Match loguru/logust format: time | level | module:function:line - message
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    )
    handler.setFormatter(formatter)
    py_logger.addHandler(handler)

    return py_logger


def setup_loguru(log_file: Path | None = None) -> Any:
    """Set up loguru logger."""
    try:
        from loguru import logger as loguru_logger

        loguru_logger.remove()  # Remove default handler
        if log_file:
            loguru_logger.add(str(log_file), level="DEBUG")

        return loguru_logger
    except ImportError:
        return None


def setup_logust(log_file: Path | None = None) -> Any:
    """Set up logust logger."""
    from logust import Logger, LogLevel
    from logust._logust import PyLogger

    inner = PyLogger(LogLevel.Trace)
    logust_logger = Logger(inner)
    logust_logger.disable()  # Disable console

    if log_file:
        logust_logger.add(str(log_file))  # Uses sync writes (default)

    return logust_logger


def benchmark_simple_no_output() -> dict[str, float]:
    """Benchmark simple log calls with no output (fastest case)."""
    results = {}

    # Python logging with NullHandler
    py_logger = setup_python_logging(None)
    start = time.perf_counter()
    for i in range(N):
        py_logger.info("Simple message %d", i)
    results["logging"] = time.perf_counter() - start

    # loguru (if available)
    loguru_logger = setup_loguru(None)
    if loguru_logger:
        start = time.perf_counter()
        for i in range(N):
            loguru_logger.info("Simple message {}", i)
        results["loguru"] = time.perf_counter() - start

    # logust
    logust_logger = setup_logust(None)
    start = time.perf_counter()
    for i in range(N):
        logust_logger.info(f"Simple message {i}")
    results["logust"] = time.perf_counter() - start

    return results


def benchmark_file_write() -> dict[str, float]:
    """Benchmark writing logs to file."""
    results = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Python logging
        log_file = tmppath / "logging.log"
        py_logger = setup_python_logging(log_file)
        start = time.perf_counter()
        for i in range(N):
            py_logger.info("File message %d", i)
        for handler in py_logger.handlers:
            handler.flush()
        results["logging"] = time.perf_counter() - start

        # loguru
        log_file = tmppath / "loguru.log"
        loguru_logger = setup_loguru(log_file)
        if loguru_logger:
            start = time.perf_counter()
            for i in range(N):
                loguru_logger.info("File message {}", i)
            loguru_logger.complete()
            results["loguru"] = time.perf_counter() - start
            loguru_logger.remove()

        # logust
        log_file = tmppath / "logust.log"
        logust_logger = setup_logust(log_file)
        start = time.perf_counter()
        for i in range(N):
            logust_logger.info(f"File message {i}")
        logust_logger.complete()
        results["logust"] = time.perf_counter() - start

    return results


def benchmark_formatted() -> dict[str, float]:
    """Benchmark formatted log messages."""
    results = {}
    user_id = "user_12345"
    action = "login"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Python logging
        log_file = tmppath / "logging.log"
        py_logger = setup_python_logging(log_file)
        start = time.perf_counter()
        for i in range(N):
            py_logger.info("User %s performed action %s (count: %d)", user_id, action, i)
        for handler in py_logger.handlers:
            handler.flush()
        results["logging"] = time.perf_counter() - start

        # loguru
        log_file = tmppath / "loguru.log"
        loguru_logger = setup_loguru(log_file)
        if loguru_logger:
            start = time.perf_counter()
            for i in range(N):
                loguru_logger.info("User {} performed action {} (count: {})", user_id, action, i)
            loguru_logger.complete()
            results["loguru"] = time.perf_counter() - start
            loguru_logger.remove()

        # logust
        log_file = tmppath / "logust.log"
        logust_logger = setup_logust(log_file)
        start = time.perf_counter()
        for i in range(N):
            logust_logger.info(f"User {user_id} performed action {action} (count: {i})")
        logust_logger.complete()
        results["logust"] = time.perf_counter() - start

    return results


def benchmark_json_serialize() -> dict[str, float]:
    """Benchmark JSON serialization."""
    results = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Python logging doesn't have built-in JSON, skip
        results["logging"] = float("nan")

        # loguru with serialize
        try:
            from loguru import logger as loguru_logger

            log_file = tmppath / "loguru.json"
            loguru_logger.remove()
            loguru_logger.add(str(log_file), serialize=True, level="DEBUG")

            start = time.perf_counter()
            for i in range(N):
                loguru_logger.info("JSON message {}", i)
            loguru_logger.complete()
            results["loguru"] = time.perf_counter() - start
            loguru_logger.remove()
        except ImportError:
            pass

        # logust with serialize
        log_file = tmppath / "logust.json"
        logust_logger = setup_logust(None)
        logust_logger.add(str(log_file), serialize=True)
        start = time.perf_counter()
        for i in range(N):
            logust_logger.info(f"JSON message {i}")
        logust_logger.complete()
        results["logust"] = time.perf_counter() - start

    return results


def benchmark_with_context() -> dict[str, float]:
    """Benchmark logging with bound context."""
    results = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Python logging doesn't have context binding, skip
        results["logging"] = float("nan")

        # loguru with bind
        try:
            from loguru import logger as loguru_logger

            log_file = tmppath / "loguru.log"
            loguru_logger.remove()
            loguru_logger.add(str(log_file), level="DEBUG")
            bound_loguru = loguru_logger.bind(user_id=123, session="abc")

            start = time.perf_counter()
            for i in range(N):
                bound_loguru.info("Context message {}", i)
            loguru_logger.complete()
            results["loguru"] = time.perf_counter() - start
            loguru_logger.remove()
        except ImportError:
            pass

        # logust with bind
        log_file = tmppath / "logust.log"
        logust_logger = setup_logust(log_file)
        bound_logust = logust_logger.bind(user_id=123, session="abc")

        start = time.perf_counter()
        for i in range(N):
            bound_logust.info(f"Context message {i}")
        logust_logger.complete()
        results["logust"] = time.perf_counter() - start

    return results


def benchmark_async_write() -> dict[str, float]:
    """Benchmark async/enqueue file writes."""
    results = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Python logging doesn't have built-in async, skip
        results["logging"] = float("nan")

        # loguru with enqueue=True
        try:
            from loguru import logger as loguru_logger

            log_file = tmppath / "loguru_async.log"
            loguru_logger.remove()
            loguru_logger.add(str(log_file), level="DEBUG", enqueue=True)

            start = time.perf_counter()
            for i in range(N):
                loguru_logger.info("Async message {}", i)
            loguru_logger.complete()
            results["loguru"] = time.perf_counter() - start
            loguru_logger.remove()
        except ImportError:
            pass

        # logust with enqueue=True
        log_file = tmppath / "logust_async.log"
        logust_logger = setup_logust(None)
        logust_logger.add(str(log_file), enqueue=True)
        start = time.perf_counter()
        for i in range(N):
            logust_logger.info(f"Async message {i}")
        logust_logger.complete()
        results["logust"] = time.perf_counter() - start

    return results


def benchmark_async_with_context() -> dict[str, float]:
    """Benchmark async writes with bound context."""
    results = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Python logging doesn't have context binding, skip
        results["logging"] = float("nan")

        # loguru with enqueue=True and bind
        try:
            from loguru import logger as loguru_logger

            log_file = tmppath / "loguru_async_ctx.log"
            loguru_logger.remove()
            loguru_logger.add(str(log_file), level="DEBUG", enqueue=True)
            bound_loguru = loguru_logger.bind(user_id=123, session="abc")

            start = time.perf_counter()
            for i in range(N):
                bound_loguru.info("Async context message {}", i)
            loguru_logger.complete()
            results["loguru"] = time.perf_counter() - start
            loguru_logger.remove()
        except ImportError:
            pass

        # logust with enqueue=True and bind
        log_file = tmppath / "logust_async_ctx.log"
        logust_logger = setup_logust(None)
        logust_logger.add(str(log_file), enqueue=True)
        bound_logust = logust_logger.bind(user_id=123, session="abc")

        start = time.perf_counter()
        for i in range(N):
            bound_logust.info(f"Async context message {i}")
        logust_logger.complete()
        results["logust"] = time.perf_counter() - start

    return results


def benchmark_async_nonblocking() -> dict[str, float]:
    """Benchmark async without waiting - measures main thread latency only.

    This measures the true benefit of async: how fast can we return to the caller?
    We DON'T call complete() before timing ends, so we only measure queue time.
    """
    results = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        results["logging"] = float("nan")

        # loguru with enqueue=True (non-blocking)
        try:
            from loguru import logger as loguru_logger

            log_file = tmppath / "loguru_nonblock.log"
            loguru_logger.remove()
            loguru_logger.add(str(log_file), level="DEBUG", enqueue=True)

            start = time.perf_counter()
            for i in range(N):
                loguru_logger.info("Non-blocking message {}", i)
            # NO complete() - just measure queue time
            results["loguru"] = time.perf_counter() - start

            # Cleanup after timing
            loguru_logger.complete()
            loguru_logger.remove()
        except ImportError:
            pass

        # logust with enqueue=True (non-blocking)
        log_file = tmppath / "logust_nonblock.log"
        logust_logger = setup_logust(None)
        logust_logger.add(str(log_file), enqueue=True)

        start = time.perf_counter()
        for i in range(N):
            logust_logger.info(f"Non-blocking message {i}")
        # NO complete() - just measure queue time
        results["logust"] = time.perf_counter() - start

        # Cleanup after timing
        logust_logger.complete()

    return results


def benchmark_sync_vs_async_latency() -> dict[str, dict[str, float]]:
    """Compare sync vs async latency for both libraries.

    Returns dict with 'sync' and 'async' sub-dicts for comparison.
    """
    results = {"sync": {}, "async": {}}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # loguru sync
        try:
            from loguru import logger as loguru_logger

            log_file = tmppath / "loguru_sync.log"
            loguru_logger.remove()
            loguru_logger.add(str(log_file), level="DEBUG", enqueue=False)

            start = time.perf_counter()
            for i in range(N):
                loguru_logger.info("Sync message {}", i)
            results["sync"]["loguru"] = time.perf_counter() - start
            loguru_logger.remove()

            # loguru async (non-blocking)
            log_file = tmppath / "loguru_async.log"
            loguru_logger.remove()
            loguru_logger.add(str(log_file), level="DEBUG", enqueue=True)

            start = time.perf_counter()
            for i in range(N):
                loguru_logger.info("Async message {}", i)
            results["async"]["loguru"] = time.perf_counter() - start

            loguru_logger.complete()
            loguru_logger.remove()
        except ImportError:
            pass

        # logust sync
        log_file = tmppath / "logust_sync.log"
        logust_logger = setup_logust(None)
        logust_logger.add(str(log_file), enqueue=False)

        start = time.perf_counter()
        for i in range(N):
            logust_logger.info(f"Sync message {i}")
        logust_logger.complete()
        results["sync"]["logust"] = time.perf_counter() - start

        # logust async (non-blocking)
        log_file = tmppath / "logust_async.log"
        logust_logger2 = setup_logust(None)
        logust_logger2.add(str(log_file), enqueue=True)

        start = time.perf_counter()
        for i in range(N):
            logust_logger2.info(f"Async message {i}")
        results["async"]["logust"] = time.perf_counter() - start

        logust_logger2.complete()

    return results


def format_time(seconds: float) -> str:
    """Format time in human-readable format."""
    if seconds != seconds:  # NaN check
        return "N/A"
    ms = seconds * 1000
    if ms < 1:
        return f"{ms * 1000:.1f} µs"
    return f"{ms:.2f} ms"


def format_relative(base: float, target: float) -> str:
    """Format relative performance."""
    if base != base or target != target:  # NaN check
        return "N/A"
    if base == 0:
        return "N/A"
    ratio = base / target
    if ratio > 1:
        return f"{ratio:.1f}x faster"
    else:
        return f"{1/ratio:.1f}x slower"


def print_results(name: str, results: dict[str, float]) -> None:
    """Print benchmark results in a table format."""
    print(f"\n{'='*60}")
    print(f" {name} ({N:,} logs)")
    print(f"{'='*60}")
    print(f"{'Library':<15} {'Time':>12} {'vs logust':>15}")
    print(f"{'-'*42}")

    logust_time = results.get("logust", float("nan"))

    for lib in ["logging", "loguru", "logust"]:
        if lib in results:
            t = results[lib]
            time_str = format_time(t)
            if lib == "logust":
                rel_str = "(baseline)"
            else:
                rel_str = format_relative(t, logust_time)
            print(f"{lib:<15} {time_str:>12} {rel_str:>15}")


def print_latency_comparison(results: dict[str, dict[str, float]]) -> None:
    """Print sync vs async latency comparison."""
    print(f"\n{'='*60}")
    print(f" Sync vs Async Latency ({N:,} logs)")
    print(f"{'='*60}")
    print(" This shows main thread time only (async doesn't wait for I/O)")
    print(f"{'-'*60}")
    print(f"{'Library':<12} {'Sync':>12} {'Async':>12} {'Speedup':>12}")
    print(f"{'-'*48}")

    for lib in ["loguru", "logust"]:
        sync_time = results["sync"].get(lib, float("nan"))
        async_time = results["async"].get(lib, float("nan"))

        sync_str = format_time(sync_time)
        async_str = format_time(async_time)

        if sync_time == sync_time and async_time == async_time and async_time > 0:
            speedup = sync_time / async_time
            speedup_str = f"{speedup:.1f}x"
        else:
            speedup_str = "N/A"

        print(f"{lib:<12} {sync_str:>12} {async_str:>12} {speedup_str:>12}")


def run_all_benchmarks() -> None:
    """Run all benchmarks and print results."""
    print("\n" + "=" * 60)
    print(" Logust Benchmark Suite")
    print(" Comparing: Python logging, loguru, logust")
    print("=" * 60)

    # Check if loguru is available
    try:
        import loguru  # noqa: F401

        print("\n[OK] loguru is available")
    except ImportError:
        print("\n[WARN] loguru not installed, skipping loguru benchmarks")
        print("       Install with: uv pip install loguru")

    # Suppress stderr during benchmarks
    stderr_capture = io.StringIO()

    with redirect_stderr(stderr_capture):
        print("\nRunning benchmarks...")

        results = {}

        print("  [1/9] Simple (no output)...", end="", flush=True)
        results["simple"] = benchmark_simple_no_output()
        print(" done")

        print("  [2/9] File write (sync)...", end="", flush=True)
        results["file"] = benchmark_file_write()
        print(" done")

        print("  [3/9] Formatted...", end="", flush=True)
        results["formatted"] = benchmark_formatted()
        print(" done")

        print("  [4/9] JSON serialize...", end="", flush=True)
        results["json"] = benchmark_json_serialize()
        print(" done")

        print("  [5/9] With context (sync)...", end="", flush=True)
        results["context"] = benchmark_with_context()
        print(" done")

        print("  [6/9] File write (async)...", end="", flush=True)
        results["async"] = benchmark_async_write()
        print(" done")

        print("  [7/9] With context (async)...", end="", flush=True)
        results["async_context"] = benchmark_async_with_context()
        print(" done")

        print("  [8/9] Async non-blocking...", end="", flush=True)
        results["nonblocking"] = benchmark_async_nonblocking()
        print(" done")

        print("  [9/9] Sync vs Async latency...", end="", flush=True)
        results["latency"] = benchmark_sync_vs_async_latency()
        print(" done")

    # Print all results
    print_results("Simple (no output)", results["simple"])
    print_results("File write (sync)", results["file"])
    print_results("Formatted", results["formatted"])
    print_results("JSON serialize", results["json"])
    print_results("With context (sync)", results["context"])
    print_results("File write (async + complete)", results["async"])
    print_results("With context (async + complete)", results["async_context"])
    print_results("Async non-blocking (no wait)", results["nonblocking"])

    # Print sync vs async comparison
    print_latency_comparison(results["latency"])

    # Summary
    print("\n" + "=" * 60)
    print(" Summary")
    print("=" * 60)

    # Calculate average speedup
    logust_times = []
    loguru_times = []
    logging_times = []

    for result in results.values():
        if "logust" in result and result["logust"] == result["logust"]:
            logust_times.append(result["logust"])
        if "loguru" in result and result["loguru"] == result["loguru"]:
            loguru_times.append(result["loguru"])
        if "logging" in result and result["logging"] == result["logging"]:
            logging_times.append(result["logging"])

    if loguru_times and logust_times:
        avg_loguru = sum(loguru_times) / len(loguru_times)
        avg_logust = sum(logust_times) / len(logust_times)
        speedup = avg_loguru / avg_logust
        print(f"  logust vs loguru:  {speedup:.1f}x faster on average")

    if logging_times and logust_times:
        avg_logging = sum(logging_times) / len(logging_times)
        avg_logust = sum(logust_times) / len(logust_times)
        speedup = avg_logging / avg_logust
        print(f"  logust vs logging: {speedup:.1f}x faster on average")

    print()


# Pytest integration
class TestBenchmark:
    """Benchmark tests for pytest execution."""

    def test_simple_no_output(self) -> None:
        """Benchmark simple logging without output."""
        results = benchmark_simple_no_output()
        print_results("Simple (no output)", results)
        assert "logust" in results
        assert results["logust"] > 0

    def test_file_write(self) -> None:
        """Benchmark file writing."""
        results = benchmark_file_write()
        print_results("File write", results)
        assert "logust" in results
        assert results["logust"] > 0

    def test_formatted(self) -> None:
        """Benchmark formatted messages."""
        results = benchmark_formatted()
        print_results("Formatted", results)
        assert "logust" in results
        assert results["logust"] > 0

    def test_json_serialize(self) -> None:
        """Benchmark JSON serialization."""
        results = benchmark_json_serialize()
        print_results("JSON serialize", results)
        assert "logust" in results
        assert results["logust"] > 0

    def test_with_context(self) -> None:
        """Benchmark context binding."""
        results = benchmark_with_context()
        print_results("With context (sync)", results)
        assert "logust" in results
        assert results["logust"] > 0

    def test_async_write(self) -> None:
        """Benchmark async file writing."""
        results = benchmark_async_write()
        print_results("File write (async)", results)
        assert "logust" in results
        assert results["logust"] > 0

    def test_async_with_context(self) -> None:
        """Benchmark async with context binding."""
        results = benchmark_async_with_context()
        print_results("With context (async)", results)
        assert "logust" in results
        assert results["logust"] > 0

    def test_async_nonblocking(self) -> None:
        """Benchmark async non-blocking (queue time only)."""
        results = benchmark_async_nonblocking()
        print_results("Async non-blocking", results)
        assert "logust" in results
        assert results["logust"] > 0

    def test_sync_vs_async_latency(self) -> None:
        """Benchmark sync vs async latency comparison."""
        results = benchmark_sync_vs_async_latency()
        print_latency_comparison(results)
        assert "logust" in results["sync"]
        assert "logust" in results["async"]
        assert results["sync"]["logust"] > 0
        assert results["async"]["logust"] > 0


if __name__ == "__main__":
    run_all_benchmarks()
