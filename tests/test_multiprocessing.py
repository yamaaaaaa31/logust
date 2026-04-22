"""Regression tests for multiprocessing support (issue #22).

A forked child process inherits the parent's FileSink memory, but the
background writer thread created by ``thread::spawn`` does not survive
fork — only the calling thread does. Without PID-aware Drop, the child's
inherited ``JoinHandle`` references a non-existent thread and ``join()``
panics with "threads should not terminate unexpectedly".
"""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger


def _child_remove(log_path: str) -> None:
    """Run inside a forked child: add a file handler with enqueue=True,
    then remove it. This is the exact sequence that panicked in #22.
    """
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    handler_id = logger.add(log_path, level=LogLevel.Trace, enqueue=True)
    logger.info("from child")
    logger.complete()
    logger.remove(handler_id)


def _child_inherited_remove() -> None:
    """Run inside a forked child without creating a new logger: just call
    ``logger.remove()`` on the inherited parent state. The inherited
    ``FileSink`` will be dropped when its ``HandlerEntry`` is removed.
    """
    import logust

    logust.logger.remove()


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="fork start method not available on this platform",
)
class TestMultiprocessingFork:
    """Issue #22: FileSink::drop must not panic in a forked child."""

    def test_child_creates_and_removes_enqueue_sink(self, tmp_path: Path) -> None:
        ctx = multiprocessing.get_context("fork")
        log_file = tmp_path / "child.log"
        p = ctx.Process(target=_child_remove, args=(str(log_file),))
        p.start()
        p.join(timeout=30)

        assert p.exitcode == 0, (
            f"child exited with {p.exitcode} (expected 0); "
            "FileSink::drop likely panicked on the inherited JoinHandle"
        )

    @pytest.mark.skipif(
        sys.platform == "darwin",
        reason=(
            "fork() with a multi-threaded parent is unsafe on macOS "
            "(libdispatch raises SIGTRAP independently of this bug)"
        ),
    )
    def test_child_drops_inherited_enqueue_sink(self, tmp_path: Path) -> None:
        """Parent creates an enqueue=True sink, forks, child removes handlers."""
        import logust

        log_file = tmp_path / "inherited.log"
        handler_id = logust.logger.add(
            log_file, level=LogLevel.Trace, enqueue=True
        )
        try:
            ctx = multiprocessing.get_context("fork")
            p = ctx.Process(target=_child_inherited_remove)
            p.start()
            p.join(timeout=30)

            assert p.exitcode == 0, (
                f"child exited with {p.exitcode} (expected 0); "
                "inherited FileSink::drop likely panicked"
            )
        finally:
            logust.logger.remove(handler_id)
