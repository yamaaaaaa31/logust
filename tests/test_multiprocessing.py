"""Regression tests for multiprocessing support (issue #22).

A forked child process inherits the parent's ``FileSink`` memory, but an
``enqueue=True`` sink owns thread/channel state that must be rebuilt in the
child. These tests cover both the original panic and the follow-up fix that
restarts the writer in forked children so parent/child processes can append
to the same sink safely.
"""

from __future__ import annotations

import multiprocessing
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


def _child_inherited_write_batch(
    start_event: multiprocessing.synchronize.Event,
    prefix: str,
    count: int,
) -> None:
    """Run inside a forked child using the inherited global logger state."""
    import logust

    assert start_event.wait(timeout=10), "start_event was never set"

    for i in range(count):
        logust.logger.info(f"{prefix}|{i:03d}|")

    logust.logger.complete()


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

    def test_parent_and_children_share_inherited_enqueue_sink(
        self, tmp_path: Path
    ) -> None:
        """Forked children lazily restart their writer and append without loss."""
        import logust

        log_file = tmp_path / "shared.log"
        handler_id = logust.logger.add(
            log_file, level=LogLevel.Trace, enqueue=True
        )

        child_count = 3
        messages_per_process = 40
        ctx = multiprocessing.get_context("fork")
        start_event = ctx.Event()
        processes = [
            ctx.Process(
                target=_child_inherited_write_batch,
                args=(start_event, f"child-{idx}", messages_per_process),
            )
            for idx in range(child_count)
        ]

        try:
            for process in processes:
                process.start()

            start_event.set()

            for i in range(messages_per_process):
                logust.logger.info(f"parent|{i:03d}|")

            for process in processes:
                process.join(timeout=30)
                assert process.exitcode == 0, (
                    f"child exited with {process.exitcode} (expected 0); "
                    "forked writer restart likely failed"
                )

            logust.logger.complete()

            lines = log_file.read_text().splitlines()
            expected_tokens = [
                *(f"parent|{i:03d}|" for i in range(messages_per_process)),
                *(
                    f"child-{child_idx}|{i:03d}|"
                    for child_idx in range(child_count)
                    for i in range(messages_per_process)
                ),
            ]

            assert len(lines) == len(expected_tokens)
            for token in expected_tokens:
                assert sum(token in line for line in lines) == 1, (
                    f"missing or duplicated log line for token {token!r}"
                )
        finally:
            logust.logger.remove(handler_id)
