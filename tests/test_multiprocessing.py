"""Regression tests for multiprocessing support (issue #22).

A forked child process inherits the parent's ``FileSink`` memory, but an
``enqueue=True`` sink owns thread/channel state that must be rebuilt in the
child. These tests cover both the original panic and the follow-up fix that
restarts the writer in forked children so parent/child processes can append
to the same sink safely.
"""

from __future__ import annotations

import gzip
import multiprocessing
import os
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path
import tempfile

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger

_INHERITED_TEST_LOGGER: Logger | None = None


def _active_fork_logger() -> Logger:
    if _INHERITED_TEST_LOGGER is not None:
        return _INHERITED_TEST_LOGGER

    import logust

    return logust.logger


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
    payload: str = "",
) -> None:
    """Run inside a forked child using the inherited global logger state."""
    assert start_event.wait(timeout=10), "start_event was never set"
    logger = _active_fork_logger()

    for i in range(count):
        logger.info(f"{prefix}|{i:03d}|{payload}")

    logger.complete()


def _child_inherited_write_once(token: str) -> None:
    """Run inside a forked child and append a single inherited-log token."""
    logger = _active_fork_logger()
    logger.info(token)
    logger.complete()


def _child_nested_fork_writer(
    parent_token: str,
    grandchild_token: str,
) -> None:
    """Run in a child process and trigger a nested fork once."""
    logger = _active_fork_logger()
    ctx = multiprocessing.get_context("fork")
    grandchild = ctx.Process(
        target=_child_inherited_write_once,
        args=(grandchild_token,),
    )
    grandchild.start()
    grandchild.join(timeout=30)

    if grandchild.exitcode is None:
        os._exit(1)

    if grandchild.exitcode != 0:
        os._exit(1)

    logger.info(parent_token)
    logger.complete()


def _read_aggregated_log_lines(log_file: Path) -> list[str]:
    """Read the active log plus every rotated raw/gzip file for the same sink."""
    lines: list[str] = []
    stem = log_file.stem
    lock_name = f"{log_file.name}.lock"

    for path in sorted(log_file.parent.iterdir()):
        if path.name == lock_name:
            continue
        if path == log_file or path.name.startswith(f"{stem}."):
            if path.suffix == ".gz":
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    lines.extend(fh.read().splitlines())
            else:
                lines.extend(path.read_text().splitlines())

    return lines


def _assert_exact_log_tokens(log_file: Path, expected_tokens: list[str]) -> None:
    actual = Counter(_read_aggregated_log_lines(log_file))
    expected = Counter(expected_tokens)
    assert actual == expected, (
        "aggregated log tokens did not match exactly; "
        f"missing={expected - actual}, extra={actual - expected}"
    )


def _run_module_scenario(function_name: str, *, timeout: float | None = None) -> None:
    script = (
        "import runpy; "
        f"ns = runpy.run_path({str(Path(__file__).resolve())!r}); "
        f"ns[{function_name!r}]()"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"scenario {function_name} timed out after {exc.timeout} seconds\n"
            f"stdout:\n{exc.stdout or ''}\n"
            f"stderr:\n{exc.stderr or ''}"
        )
    if result.returncode != 0:
        pytest.fail(
            f"scenario {function_name} failed with exit code {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def _scenario_parent_and_children_share_inherited_enqueue_sink() -> None:
    global _INHERITED_TEST_LOGGER

    tmp_path = Path(tempfile.mkdtemp())
    log_file = tmp_path / "shared.log"
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.disable()
    _INHERITED_TEST_LOGGER = logger
    handler_id = logger.add(log_file, level=LogLevel.Trace, enqueue=True)

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
            logger.info(f"parent|{i:03d}|")

        for process in processes:
            exitcode = _join_process_or_fail(
                process,
                context="forked writer restart likely failed",
            )
            assert exitcode == 0, (
                f"child exited with {exitcode} (expected 0); "
                "forked writer restart likely failed"
            )

        logger.complete()

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
        logger.remove(handler_id)
        _INHERITED_TEST_LOGGER = None


def _scenario_shared_enqueue_rotation_with_compression_has_no_loss() -> None:
    global _INHERITED_TEST_LOGGER

    tmp_path = Path(tempfile.mkdtemp())
    log_file = tmp_path / "rotation-compression.log"
    payload = "x" * 96
    child_count = 3
    messages_per_process = 60
    ctx = multiprocessing.get_context("fork")
    start_event = ctx.Event()
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.disable()
    _INHERITED_TEST_LOGGER = logger
    handler_id = logger.add(
        log_file,
        level=LogLevel.Trace,
        format="{message}",
        rotation="1 KB",
        compression=True,
        enqueue=True,
    )
    processes = [
        ctx.Process(
            target=_child_inherited_write_batch,
            args=(start_event, f"child-{idx}", messages_per_process, payload),
        )
        for idx in range(child_count)
    ]
    expected_tokens = [
        *(f"parent|{i:03d}|{payload}" for i in range(messages_per_process)),
        *(
            f"child-{child_idx}|{i:03d}|{payload}"
            for child_idx in range(child_count)
            for i in range(messages_per_process)
        ),
    ]

    try:
        for process in processes:
            process.start()

        start_event.set()

        for i in range(messages_per_process):
            logger.info(f"parent|{i:03d}|{payload}")

        for process in processes:
            exitcode = _join_process_or_fail(
                process,
                context="rotation+compression shared enqueue writer likely lost safety",
            )
            assert exitcode == 0

        logger.complete()

        rotated_files = [path for path in tmp_path.iterdir() if path.suffix == ".gz"]
        assert rotated_files, "expected at least one compressed rotated file"
        _assert_exact_log_tokens(log_file, expected_tokens)
    finally:
        logger.remove(handler_id)
        _INHERITED_TEST_LOGGER = None


def _scenario_shared_enqueue_rotation_with_retention_has_no_loss() -> None:
    global _INHERITED_TEST_LOGGER

    tmp_path = Path(tempfile.mkdtemp())
    log_file = tmp_path / "rotation-retention.log"
    payload = "y" * 96
    child_count = 3
    messages_per_process = 60
    ctx = multiprocessing.get_context("fork")
    start_event = ctx.Event()

    stale_files = []
    for idx in range(3):
        stale_path = tmp_path / f"rotation-retention.2000-01-0{idx + 1}_00-00-00_000000.pid0.log"
        stale_path.write_text(f"stale-{idx}\n")
        old_time = time.time() - 10 * 24 * 60 * 60
        os.utime(stale_path, (old_time, old_time))
        stale_files.append(stale_path)

    logger = Logger(PyLogger(LogLevel.Trace))
    logger.disable()
    _INHERITED_TEST_LOGGER = logger
    handler_id = logger.add(
        log_file,
        level=LogLevel.Trace,
        format="{message}",
        rotation="1 KB",
        retention="1 day",
        enqueue=True,
    )
    processes = [
        ctx.Process(
            target=_child_inherited_write_batch,
            args=(start_event, f"child-{idx}", messages_per_process, payload),
        )
        for idx in range(child_count)
    ]
    expected_tokens = [
        *(f"parent|{i:03d}|{payload}" for i in range(messages_per_process)),
        *(
            f"child-{child_idx}|{i:03d}|{payload}"
            for child_idx in range(child_count)
            for i in range(messages_per_process)
        ),
    ]

    try:
        for process in processes:
            process.start()

        start_event.set()

        for i in range(messages_per_process):
            logger.info(f"parent|{i:03d}|{payload}")

        for process in processes:
            exitcode = _join_process_or_fail(
                process,
                context="rotation+retention shared enqueue writer likely lost safety",
            )
            assert exitcode == 0

        logger.complete()

        for stale_path in stale_files:
            assert not stale_path.exists(), f"retention did not remove {stale_path.name}"

        lock_path = Path(f"{log_file}.lock")
        assert lock_path.exists(), "retention must not remove lock file"

        _assert_exact_log_tokens(log_file, expected_tokens)
    finally:
        logger.remove(handler_id)
        _INHERITED_TEST_LOGGER = None


def _scenario_fork_while_other_thread_is_logging_does_not_deadlock() -> None:
    global _INHERITED_TEST_LOGGER

    tmp_path = Path(tempfile.mkdtemp())
    log_file = tmp_path / "fork-race.log"
    stop_event = threading.Event()
    background_started = threading.Event()
    background_errors: list[BaseException] = []
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.disable()
    _INHERITED_TEST_LOGGER = logger
    handler_id = logger.add(
        log_file,
        level=LogLevel.Trace,
        format="{message}",
        enqueue=True,
    )

    def _background_writer() -> None:
        try:
            i = 0
            background_started.set()
            while not stop_event.is_set():
                logger.info(f"background|{i:05d}|")
                i += 1
        except BaseException as exc:
            background_errors.append(exc)

    thread = threading.Thread(target=_background_writer, daemon=True)
    thread.start()

    ctx = multiprocessing.get_context("fork")
    child_tokens = [f"fork-child-{idx:03d}|000|" for idx in range(100)]

    try:
        assert background_started.wait(timeout=5), (
            "background writer did not start logging loop"
        )
        time.sleep(0.05)

        for token in child_tokens:
            process = ctx.Process(
                target=_child_inherited_write_once,
                args=(token,),
            )
            process.start()
            exitcode = _join_process_or_fail(
                process,
                timeout=5,
                context="fork while background logging likely deadlocked in atfork",
            )
            assert exitcode == 0

        stop_event.set()
        thread.join(timeout=10)
        assert not thread.is_alive(), "background logging thread did not stop"
        assert not background_errors, f"background logging thread failed: {background_errors}"

        logger.complete()
        lines = _read_aggregated_log_lines(log_file)
        assert any(
            line.startswith("background|") for line in lines
        ), "background logging thread produced no output"
        for token in child_tokens:
            assert lines.count(token) == 1, f"missing or duplicated child token {token!r}"
    finally:
        stop_event.set()
        thread.join(timeout=10)
        logger.remove(handler_id)
        _INHERITED_TEST_LOGGER = None


def _scenario_nested_fork_logging_works() -> None:
    global _INHERITED_TEST_LOGGER

    tmp_path = Path(tempfile.mkdtemp())
    log_file = tmp_path / "nested-fork.log"
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.disable()
    _INHERITED_TEST_LOGGER = logger
    handler_id = logger.add(
        log_file,
        level=LogLevel.Trace,
        format="{message}",
        enqueue=True,
    )

    child_token = "nested-child"
    grandchild_token = "nested-grandchild"
    parent_token = "nested-parent"

    try:
        ctx = multiprocessing.get_context("fork")
        process = ctx.Process(
            target=_child_nested_fork_writer,
            args=(child_token, grandchild_token),
        )
        process.start()
        exitcode = _join_process_or_fail(
            process,
            context="nested fork child/grandchild logging likely failed",
        )
        assert exitcode == 0
        logger.info(parent_token)

        logger.complete()

        lines = _read_aggregated_log_lines(log_file)
        assert lines.count(parent_token) == 1
        for token in (child_token, grandchild_token):
            assert lines.count(token) == 1, f"missing token {token!r}"

    finally:
        logger.remove(handler_id)
        _INHERITED_TEST_LOGGER = None


def _join_process_or_fail(
    process: multiprocessing.process.BaseProcess,
    *,
    timeout: float = 30,
    context: str,
) -> int:
    """Join a child process and clean it up if it stops responding."""
    process.join(timeout=timeout)

    if process.is_alive():
        process.terminate()
        process.join(timeout=5)

        if process.is_alive():
            process.kill()
            process.join(timeout=5)

        pytest.fail(f"{context}: child process did not exit within {timeout} seconds")

    if process.exitcode is None:
        pytest.fail(
            f"{context}: child exitcode stayed None after join(timeout={timeout})"
        )

    return process.exitcode


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
        exitcode = _join_process_or_fail(
            p,
            context="FileSink::drop likely panicked on the inherited JoinHandle",
        )

        assert exitcode == 0, (
            f"child exited with {exitcode} (expected 0); "
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
            exitcode = _join_process_or_fail(
                p,
                context="inherited enqueue FileSink::drop likely panicked",
            )

            assert exitcode == 0, (
                f"child exited with {exitcode} (expected 0); "
                "inherited FileSink::drop likely panicked"
            )
        finally:
            logust.logger.remove(handler_id)

    def test_child_drops_inherited_sync_sink_without_duplicate_flush(
        self, tmp_path: Path
    ) -> None:
        """Forked child must not flush the parent's inherited sync buffer."""
        import logust

        log_file = tmp_path / "inherited-sync.log"
        handler_id = logust.logger.add(
            log_file, level=LogLevel.Trace, enqueue=False
        )
        try:
            logust.logger.info("parent-sync-before-fork")

            ctx = multiprocessing.get_context("fork")
            p = ctx.Process(target=_child_inherited_remove)
            p.start()
            exitcode = _join_process_or_fail(
                p,
                context="inherited sync FileSink::drop likely flushed parent buffer",
            )

            assert exitcode == 0, (
                f"child exited with {exitcode} (expected 0); "
                "inherited sync FileSink::drop likely flushed parent buffer"
            )

            logust.logger.complete()

            lines = log_file.read_text().splitlines()
            assert sum("parent-sync-before-fork" in line for line in lines) == 1
        finally:
            logust.logger.remove(handler_id)

    def test_parent_and_children_share_inherited_enqueue_sink(
        self, tmp_path: Path
    ) -> None:
        """Forked children lazily restart their writer and append without loss."""
        _run_module_scenario("_scenario_parent_and_children_share_inherited_enqueue_sink")

    def test_shared_enqueue_rotation_with_compression_has_no_loss(
        self, tmp_path: Path
    ) -> None:
        _run_module_scenario("_scenario_shared_enqueue_rotation_with_compression_has_no_loss")

    def test_shared_enqueue_rotation_with_retention_has_no_loss(
        self, tmp_path: Path
    ) -> None:
        _run_module_scenario("_scenario_shared_enqueue_rotation_with_retention_has_no_loss")

    def test_fork_while_other_thread_is_logging_does_not_deadlock(
        self, tmp_path: Path
    ) -> None:
        _run_module_scenario(
            "_scenario_fork_while_other_thread_is_logging_does_not_deadlock",
            timeout=45,
        )

    def test_nested_fork_can_log(self, tmp_path: Path) -> None:
        _run_module_scenario("_scenario_nested_fork_logging_works")
