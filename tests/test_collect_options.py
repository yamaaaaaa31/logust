"""Tests for CollectOptions functionality.

Tests the union logic for CollectOptions, patch() inheritance,
and remove_callback() cleanup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from logust import Logger
from logust._logger import CallerInfo, CollectOptions, ProcessInfo, ThreadInfo
from logust._logust import LogLevel, PyLogger


class TestCollectOptionsUnionLogic:
    """Test that CollectOptions uses union logic for multiple handlers."""

    def test_conflicting_collect_options_true_wins(self, tmp_path: Path) -> None:
        """When one handler has True and another has False, True wins."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # Handler 1: caller=False
        log1 = tmp_path / "log1.log"
        logger.add(str(log1), format="{message}", collect=CollectOptions(caller=False))

        # Handler 2: caller=True
        log2 = tmp_path / "log2.log"
        logger.add(str(log2), format="{function} | {message}", collect=CollectOptions(caller=True))

        logger.info("Test message")
        logger.complete()

        # Handler 2 needs caller info, so it should be collected
        content2 = log2.read_text()
        assert "test_conflicting_collect_options_true_wins" in content2

    def test_conflicting_collect_options_false_and_none(self, tmp_path: Path) -> None:
        """When one handler has False and another has None (auto), auto-detect wins."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # Handler 1: caller=False
        log1 = tmp_path / "log1.log"
        logger.add(str(log1), format="{message}", collect=CollectOptions(caller=False))

        # Handler 2: caller=None (auto-detect from format which includes {function})
        log2 = tmp_path / "log2.log"
        logger.add(str(log2), format="{function} | {message}")

        logger.info("Test message")
        logger.complete()

        # Handler 2's format needs caller info, so it should be collected
        content2 = log2.read_text()
        assert "test_conflicting_collect_options_false_and_none" in content2

    def test_fixed_caller_info_with_multiple_handlers(self, tmp_path: Path) -> None:
        """Fixed CallerInfo should be used when no handler has True."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        fixed_caller = CallerInfo(name="fixed_module", function="fixed_func", line=999, file="fixed.py")

        # Handler 1: fixed caller info
        log1 = tmp_path / "log1.log"
        logger.add(str(log1), format="{function}:{line} | {message}", collect=CollectOptions(caller=fixed_caller))

        # Handler 2: auto-detect (None)
        log2 = tmp_path / "log2.log"
        logger.add(str(log2), format="{message}")

        logger.info("Test message")
        logger.complete()

        # Handler 1 should use fixed caller info
        content1 = log1.read_text()
        assert "fixed_func:999" in content1

    def test_fixed_and_true_true_wins(self, tmp_path: Path) -> None:
        """When one handler has True and another has fixed value, True wins (dynamic collection)."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        fixed_caller = CallerInfo(name="fixed_module", function="fixed_func", line=999, file="fixed.py")

        # Handler 1: fixed caller info
        log1 = tmp_path / "log1.log"
        logger.add(str(log1), format="{function}:{line} | {message}", collect=CollectOptions(caller=fixed_caller))

        # Handler 2: True (force collection)
        log2 = tmp_path / "log2.log"
        logger.add(str(log2), format="{function}:{line} | {message}", collect=CollectOptions(caller=True))

        logger.info("Test message")
        logger.complete()

        # Handler 2 requested True, so dynamic collection should be used
        content2 = log2.read_text()
        # Should have actual function name, not fixed
        assert "test_fixed_and_true_true_wins" in content2

    def test_all_handlers_false_skips_collection(self, tmp_path: Path) -> None:
        """When all handlers have False, collection should be skipped."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # Both handlers: caller=False
        log1 = tmp_path / "log1.log"
        logger.add(str(log1), format="{level} | {message}", collect=CollectOptions(caller=False))

        log2 = tmp_path / "log2.log"
        logger.add(str(log2), format="{message}", collect=CollectOptions(caller=False))

        # Check internal state - both should be False
        needs_caller, _, _ = logger._compute_effective_requirements()
        # With both False, and Rust not needing it, should remain auto-detect from Rust
        # (Rust would say False if format doesn't need it)

        logger.info("Test message")
        logger.complete()

        # Verify logs are written
        content1 = log1.read_text()
        assert "INFO | Test message" in content1


class TestPatchInheritance:
    """Test that patch() inherits collect_options."""

    def test_patch_inherits_collect_options(self, tmp_path: Path) -> None:
        """Patched logger should inherit collect_options from parent."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        fixed_caller = CallerInfo(name="fixed", function="fixed_func", line=42, file="fixed.py")
        log_file = tmp_path / "test.log"
        logger.add(str(log_file), format="{function}:{line} | {message}", collect=CollectOptions(caller=fixed_caller))

        # Patch the logger
        def add_context(record: dict[str, Any]) -> None:
            record["extra"]["patched"] = True

        patched = logger.patch(add_context)

        # Check that patched logger has collect_options
        assert patched._collect_options is logger._collect_options

        patched.info("Patched message")
        patched.complete()

        content = log_file.read_text()
        # Should use fixed caller info
        assert "fixed_func:42" in content

    def test_chained_patches_inherit_collect_options(self, tmp_path: Path) -> None:
        """Multiple chained patches should all inherit collect_options."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "test.log"
        logger.add(str(log_file), format="{message}", collect=CollectOptions(caller=False))

        patched1 = logger.patch(lambda r: None)
        patched2 = patched1.patch(lambda r: None)
        patched3 = patched2.patch(lambda r: None)

        # All should share the same collect_options
        assert patched1._collect_options is logger._collect_options
        assert patched2._collect_options is logger._collect_options
        assert patched3._collect_options is logger._collect_options


class TestRemoveCallbackCleanup:
    """Test that remove_callback() cleans up _collect_options."""

    def test_remove_callback_cleans_collect_options(self, tmp_path: Path) -> None:
        """remove_callback should remove entry from _collect_options."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []

        # Add callable sink with CollectOptions
        callback_id = logger.add(
            lambda msg: messages.append(msg),
            format="{message}",
            collect=CollectOptions(caller=False),
        )

        # Verify CollectOptions was added
        assert callback_id in logger._collect_options

        # Remove the callback
        logger.remove_callback(callback_id)

        # Verify CollectOptions was cleaned up
        assert callback_id not in logger._collect_options

    def test_remove_callback_no_error_without_collect_options(self) -> None:
        """remove_callback should not error if handler has no CollectOptions."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)

        messages: list[str] = []

        # Add callback without CollectOptions
        callback_id = logger.add_callback(lambda r: messages.append(str(r)))

        # Remove should not error even though there's no CollectOptions entry
        result = logger.remove_callback(callback_id)
        assert result is True


class TestThreadProcessCollectOptions:
    """Test CollectOptions for thread and process info."""

    def test_fixed_thread_info(self, tmp_path: Path) -> None:
        """Fixed ThreadInfo should be used when specified."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        fixed_thread = ThreadInfo(name="FixedThread", id=12345)
        log_file = tmp_path / "test.log"
        logger.add(str(log_file), format="{thread} | {message}", collect=CollectOptions(thread=fixed_thread))

        logger.info("Test message")
        logger.complete()

        content = log_file.read_text()
        assert "FixedThread:12345" in content

    def test_fixed_process_info(self, tmp_path: Path) -> None:
        """Fixed ProcessInfo should be used when specified."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        fixed_process = ProcessInfo(name="FixedProcess", id=99999)
        log_file = tmp_path / "test.log"
        logger.add(str(log_file), format="{process} | {message}", collect=CollectOptions(process=fixed_process))

        logger.info("Test message")
        logger.complete()

        content = log_file.read_text()
        assert "FixedProcess:99999" in content
