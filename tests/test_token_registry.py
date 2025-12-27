"""Tests for Handler Token Registry optimization and CollectOptions."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from logust import Logger, LogLevel
from logust._logust import PyLogger

# ============================================================================
# Test CollectOptions and related data classes
# ============================================================================


class TestCollectOptionsDataClasses:
    """Test CollectOptions and CallerInfo/ThreadInfo/ProcessInfo classes."""

    def test_caller_info_defaults(self) -> None:
        """CallerInfo should have sensible defaults."""
        from logust import CallerInfo

        info = CallerInfo()
        assert info.name == ""
        assert info.function == ""
        assert info.line == 0
        assert info.file == ""

    def test_caller_info_with_values(self) -> None:
        """CallerInfo should accept custom values."""
        from logust import CallerInfo

        info = CallerInfo(name="mymodule", function="myfunc", line=42, file="app.py")
        assert info.name == "mymodule"
        assert info.function == "myfunc"
        assert info.line == 42
        assert info.file == "app.py"

    def test_thread_info_defaults(self) -> None:
        """ThreadInfo should have sensible defaults."""
        from logust import ThreadInfo

        info = ThreadInfo()
        assert info.name == ""
        assert info.id == 0

    def test_thread_info_with_values(self) -> None:
        """ThreadInfo should accept custom values."""
        from logust import ThreadInfo

        info = ThreadInfo(name="worker", id=12345)
        assert info.name == "worker"
        assert info.id == 12345

    def test_process_info_defaults(self) -> None:
        """ProcessInfo should have sensible defaults."""
        from logust import ProcessInfo

        info = ProcessInfo()
        assert info.name == ""
        assert info.id == 0

    def test_process_info_with_values(self) -> None:
        """ProcessInfo should accept custom values."""
        from logust import ProcessInfo

        info = ProcessInfo(name="main", id=99999)
        assert info.name == "main"
        assert info.id == 99999

    def test_collect_options_defaults(self) -> None:
        """CollectOptions should default to None (auto-detect)."""
        from logust import CollectOptions

        options = CollectOptions()
        assert options.caller is None
        assert options.thread is None
        assert options.process is None

    def test_collect_options_with_booleans(self) -> None:
        """CollectOptions should accept boolean values."""
        from logust import CollectOptions

        options = CollectOptions(caller=False, thread=True, process=False)
        assert options.caller is False
        assert options.thread is True
        assert options.process is False

    def test_collect_options_with_fixed_values(self) -> None:
        """CollectOptions should accept Info objects for fixed values."""
        from logust import CallerInfo, CollectOptions, ProcessInfo, ThreadInfo

        caller = CallerInfo(name="mod", function="fn", line=10, file="f.py")
        thread = ThreadInfo(name="t1", id=100)
        process = ProcessInfo(name="p1", id=200)

        options = CollectOptions(caller=caller, thread=thread, process=process)
        assert options.caller == caller
        assert options.thread == thread
        assert options.process == process


# ============================================================================
# Test Token Requirements Detection
# ============================================================================


class TestTokenRequirements:
    """Test token requirements detection from format strings."""

    def test_default_console_needs_caller(self) -> None:
        """Default console handler uses caller info in format."""
        inner = PyLogger(LogLevel.Trace)
        _logger = Logger(inner)

        # Default format: "{time} | {level:<8} | {name}:{function}:{line} - {message}"
        assert inner.needs_caller_info is True
        assert inner.needs_thread_info is False
        assert inner.needs_process_info is False

    def test_simple_format_no_caller(self, tmp_path: Path) -> None:
        """Format without caller tokens should not need caller info."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()  # Remove default console

        log_file = tmp_path / "simple.log"
        logger.add(str(log_file), format="{time} | {level} | {message}")

        assert inner.needs_caller_info is False
        assert inner.needs_thread_info is False
        assert inner.needs_process_info is False

    def test_thread_format_needs_thread(self, tmp_path: Path) -> None:
        """Format with {thread} should need thread info."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "thread.log"
        logger.add(str(log_file), format="{thread} | {message}")

        assert inner.needs_caller_info is False
        assert inner.needs_thread_info is True
        assert inner.needs_process_info is False

    def test_process_format_needs_process(self, tmp_path: Path) -> None:
        """Format with {process} should need process info."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "process.log"
        logger.add(str(log_file), format="{process} | {message}")

        assert inner.needs_caller_info is False
        assert inner.needs_thread_info is False
        assert inner.needs_process_info is True

    def test_all_tokens_format(self, tmp_path: Path) -> None:
        """Format with all tokens should need all info."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "all.log"
        logger.add(
            str(log_file),
            format="{time} | {name}:{function}:{line} | {thread} | {process} | {message}",
        )

        assert inner.needs_caller_info is True
        assert inner.needs_thread_info is True
        assert inner.needs_process_info is True

    def test_name_token_needs_caller(self, tmp_path: Path) -> None:
        """Format with {name} should need caller info."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "name.log"
        logger.add(str(log_file), format="{name} | {message}")

        assert inner.needs_caller_info is True

    def test_function_token_needs_caller(self, tmp_path: Path) -> None:
        """Format with {function} should need caller info."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "func.log"
        logger.add(str(log_file), format="{function} | {message}")

        assert inner.needs_caller_info is True

    def test_line_token_needs_caller(self, tmp_path: Path) -> None:
        """Format with {line} should need caller info."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "line.log"
        logger.add(str(log_file), format="{line} | {message}")

        assert inner.needs_caller_info is True

    def test_file_token_needs_caller(self, tmp_path: Path) -> None:
        """Format with {file} should need caller info."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "file.log"
        logger.add(str(log_file), format="{file} | {message}")

        assert inner.needs_caller_info is True

    def test_module_token_needs_caller(self, tmp_path: Path) -> None:
        """Format with {module} should need caller info (alias for name)."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "module.log"
        logger.add(str(log_file), format="{module} | {message}")

        assert inner.needs_caller_info is True


# ============================================================================
# Test Multiple Handlers Merge Requirements
# ============================================================================


class TestMultipleHandlersMergeRequirements:
    """Test that multiple handlers merge their requirements."""

    def test_merge_thread_and_process(self, tmp_path: Path) -> None:
        """Multiple handlers should merge their requirements."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # Handler 1: needs thread
        log_file1 = tmp_path / "h1.log"
        logger.add(str(log_file1), format="{thread} | {message}")

        assert inner.needs_thread_info is True
        assert inner.needs_process_info is False

        # Handler 2: needs process
        log_file2 = tmp_path / "h2.log"
        logger.add(str(log_file2), format="{process} | {message}")

        assert inner.needs_thread_info is True
        assert inner.needs_process_info is True

    def test_merge_caller_with_simple(self, tmp_path: Path) -> None:
        """Adding handler with caller tokens should enable caller collection."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # Handler 1: simple, no caller
        log_file1 = tmp_path / "simple.log"
        logger.add(str(log_file1), format="{level} | {message}")

        assert inner.needs_caller_info is False

        # Handler 2: needs caller
        log_file2 = tmp_path / "caller.log"
        logger.add(str(log_file2), format="{function}:{line} | {message}")

        assert inner.needs_caller_info is True


# ============================================================================
# Test Callback/Filter Forces All Requirements
# ============================================================================


class TestCallbackForcesAllRequirements:
    """Test that callbacks and filters need full record."""

    def test_callback_forces_all_requirements(self) -> None:
        """Callbacks need full record, so all requirements enabled."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # No handlers, no requirements
        assert inner.needs_caller_info is False

        # Add callback - should force all requirements
        messages: list[dict[str, Any]] = []
        logger.add_callback(lambda r: messages.append(r))

        assert inner.needs_caller_info is True
        assert inner.needs_thread_info is True
        assert inner.needs_process_info is True

    def test_filter_forces_all_requirements(self, tmp_path: Path) -> None:
        """Filters need full record, so all requirements enabled."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "filtered.log"
        logger.add(
            str(log_file),
            format="{message}",  # Simple format
            filter=lambda r: True,  # But has filter
        )

        assert inner.needs_caller_info is True
        assert inner.needs_thread_info is True
        assert inner.needs_process_info is True


# ============================================================================
# Test Remove Handler Updates Requirements
# ============================================================================


class TestRemoveHandlerUpdatesRequirements:
    """Test that removing handlers updates requirements."""

    def test_remove_handler_updates_requirements(self, tmp_path: Path) -> None:
        """Removing handler should update requirements."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "temp.log"
        handler_id = logger.add(str(log_file), format="{thread} | {message}")

        assert inner.needs_thread_info is True

        logger.remove(handler_id)

        assert inner.needs_thread_info is False

    def test_remove_callback_updates_requirements(self) -> None:
        """Removing callback should update requirements."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        messages: list[dict[str, Any]] = []
        callback_id = logger.add_callback(lambda r: messages.append(r))

        assert inner.needs_caller_info is True

        logger.remove_callback(callback_id)

        assert inner.needs_caller_info is False

    def test_remove_all_handlers_clears_requirements(self, tmp_path: Path) -> None:
        """Removing all handlers should clear requirements."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file1 = tmp_path / "h1.log"
        log_file2 = tmp_path / "h2.log"
        logger.add(str(log_file1), format="{thread} | {message}")
        logger.add(str(log_file2), format="{process} | {message}")

        assert inner.needs_thread_info is True
        assert inner.needs_process_info is True

        logger.remove()

        assert inner.needs_thread_info is False
        assert inner.needs_process_info is False


# ============================================================================
# Test bind() Shares Requirements
# ============================================================================


class TestBindSharesRequirements:
    """Test that child loggers from bind() share requirements."""

    def test_bind_shares_requirements(self) -> None:
        """Child loggers from bind() should share requirements."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)

        child = logger.bind(user="alice")

        # They share the same inner requirements cache
        assert inner.needs_caller_info == child._inner.needs_caller_info
        assert inner.needs_thread_info == child._inner.needs_thread_info
        assert inner.needs_process_info == child._inner.needs_process_info

    def test_bind_reflects_parent_changes(self, tmp_path: Path) -> None:
        """Changes to parent handlers should reflect in child."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        child = logger.bind(user="bob")

        # Initially no requirements
        assert inner.needs_thread_info is False
        assert child._inner.needs_thread_info is False

        # Add handler to parent
        log_file = tmp_path / "parent.log"
        logger.add(str(log_file), format="{thread} | {message}")

        # Both should reflect the change (shared Arc)
        assert inner.needs_thread_info is True
        assert child._inner.needs_thread_info is True


# ============================================================================
# Test Conditional Info Gathering (with mocks)
# ============================================================================


class TestConditionalInfoGathering:
    """Test that info gathering is actually skipped."""

    def test_caller_info_skipped_when_not_needed(self, tmp_path: Path) -> None:
        """_get_caller_info should not be called when not needed."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "simple.log"
        logger.add(str(log_file), format="{time} | {message}")

        with patch("logust._logger._get_caller_info") as mock_caller:
            logger.info("Test message")
            mock_caller.assert_not_called()

    def test_caller_info_called_when_needed(self, tmp_path: Path) -> None:
        """_get_caller_info should be called when needed."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "caller.log"
        logger.add(str(log_file), format="{function} | {message}")

        with patch("logust._logger._get_caller_info") as mock_caller:
            mock_caller.return_value = ("mod", "func", 42, "file.py")
            logger.info("Test message")
            mock_caller.assert_called_once()

    def test_thread_info_skipped_when_not_needed(self, tmp_path: Path) -> None:
        """_get_thread_info should not be called when not needed."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "simple.log"
        logger.add(str(log_file), format="{time} | {message}")

        with patch("logust._logger._get_thread_info") as mock_thread:
            logger.info("Test message")
            mock_thread.assert_not_called()

    def test_thread_info_called_when_needed(self, tmp_path: Path) -> None:
        """_get_thread_info should be called when needed."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "thread.log"
        logger.add(str(log_file), format="{thread} | {message}")

        with patch("logust._logger._get_thread_info") as mock_thread:
            mock_thread.return_value = ("MainThread", 12345)
            logger.info("Test message")
            mock_thread.assert_called_once()

    def test_process_info_skipped_when_not_needed(self, tmp_path: Path) -> None:
        """_get_process_info should not be called when not needed."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "simple.log"
        logger.add(str(log_file), format="{time} | {message}")

        with patch("logust._logger._get_process_info") as mock_process:
            logger.info("Test message")
            mock_process.assert_not_called()

    def test_process_info_called_when_needed(self, tmp_path: Path) -> None:
        """_get_process_info should be called when needed."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "process.log"
        logger.add(str(log_file), format="{process} | {message}")

        with patch("logust._logger._get_process_info") as mock_process:
            mock_process.return_value = ("MainProcess", 99999)
            logger.info("Test message")
            mock_process.assert_called_once()


# ============================================================================
# Test CollectOptions with add()
# ============================================================================


class TestCollectOptionsWithAdd:
    """Test CollectOptions parameter in add()."""

    def test_collect_false_skips_caller(self, tmp_path: Path) -> None:
        """collect=CollectOptions(caller=False) should skip caller info."""
        from logust import CollectOptions

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "no_caller.log"
        # Format uses {function} but collect says not to collect
        logger.add(
            str(log_file),
            format="{function} | {message}",
            collect=CollectOptions(caller=False),
        )

        with patch("logust._logger._get_caller_info") as mock_caller:
            logger.info("Test message")
            mock_caller.assert_not_called()

        # Flush to ensure log is written
        logger.complete()

        # Log should have empty function
        content = log_file.read_text()
        assert " | Test message" in content

    def test_collect_true_forces_caller(self, tmp_path: Path) -> None:
        """collect=CollectOptions(caller=True) should force caller collection."""
        from logust import CollectOptions

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "force_caller.log"
        # Format doesn't use caller tokens but collect says to collect
        logger.add(
            str(log_file),
            format="{level} | {message}",
            collect=CollectOptions(caller=True),
        )

        with patch("logust._logger._get_caller_info") as mock_caller:
            mock_caller.return_value = ("mod", "func", 42, "file.py")
            logger.info("Test message")
            mock_caller.assert_called_once()

    def test_collect_fixed_caller_value(self, tmp_path: Path) -> None:
        """collect=CollectOptions(caller=CallerInfo(...)) should use fixed value."""
        from logust import CallerInfo, CollectOptions

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "fixed_caller.log"
        logger.add(
            str(log_file),
            format="{name}:{function}:{line} | {message}",
            collect=CollectOptions(
                caller=CallerInfo(
                    name="custom_mod", function="custom_fn", line=999, file="custom.py"
                )
            ),
        )

        with patch("logust._logger._get_caller_info") as mock_caller:
            logger.info("Test message")
            # Should NOT call _get_caller_info - using fixed value
            mock_caller.assert_not_called()

        logger.complete()
        content = log_file.read_text()
        assert "custom_mod:custom_fn:999 | Test message" in content

    def test_collect_fixed_thread_value(self, tmp_path: Path) -> None:
        """collect=CollectOptions(thread=ThreadInfo(...)) should use fixed value."""
        from logust import CollectOptions, ThreadInfo

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "fixed_thread.log"
        logger.add(
            str(log_file),
            format="{thread} | {message}",
            collect=CollectOptions(thread=ThreadInfo(name="WorkerThread", id=42)),
        )

        with patch("logust._logger._get_thread_info") as mock_thread:
            logger.info("Test message")
            mock_thread.assert_not_called()

        logger.complete()
        content = log_file.read_text()
        assert "WorkerThread:42 | Test message" in content

    def test_collect_fixed_process_value(self, tmp_path: Path) -> None:
        """collect=CollectOptions(process=ProcessInfo(...)) should use fixed value."""
        from logust import CollectOptions, ProcessInfo

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "fixed_process.log"
        logger.add(
            str(log_file),
            format="{process} | {message}",
            collect=CollectOptions(process=ProcessInfo(name="Worker", id=1234)),
        )

        with patch("logust._logger._get_process_info") as mock_process:
            logger.info("Test message")
            mock_process.assert_not_called()

        logger.complete()
        content = log_file.read_text()
        assert "Worker:1234 | Test message" in content

    def test_collect_mixed_options(self, tmp_path: Path) -> None:
        """CollectOptions can mix True/False/fixed values."""
        from logust import CallerInfo, CollectOptions

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "mixed.log"
        logger.add(
            str(log_file),
            format="{name} | {thread} | {process} | {message}",
            collect=CollectOptions(
                caller=CallerInfo(name="fixed_mod", function="fn", line=1, file="f.py"),
                thread=True,  # Collect real thread info
                process=False,  # Don't collect process info
            ),
        )

        logger.info("Test message")
        logger.complete()

        content = log_file.read_text()
        assert "fixed_mod |" in content


# ============================================================================
# Test Callable Sink with CollectOptions
# ============================================================================


class TestCallableSinkWithCollectOptions:
    """Test callable sinks with CollectOptions."""

    def test_callable_sink_respects_collect_options(self) -> None:
        """Callable sinks should respect CollectOptions."""
        from logust import CallerInfo, CollectOptions

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        messages: list[str] = []
        logger.add(
            lambda msg: messages.append(msg),
            format="{name}:{function} | {message}",
            collect=CollectOptions(
                caller=CallerInfo(name="lambda_mod", function="lambda_fn", line=0, file="")
            ),
        )

        logger.info("Callable test")

        assert len(messages) == 1
        assert "lambda_mod:lambda_fn | Callable test" in messages[0]


# ============================================================================
# Test Console Handler with CollectOptions
# ============================================================================


class TestConsoleWithCollectOptions:
    """Test console handler with CollectOptions."""

    def test_console_respects_collect_false(self) -> None:
        """Console handler should respect collect=False by not calling _get_caller_info."""
        from unittest.mock import patch

        from logust import CollectOptions

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # Add console with collect=False for caller
        import sys

        logger.add(
            sys.stderr,
            format="{function} | {message}",
            collect=CollectOptions(caller=False),
        )

        # Verify that _get_caller_info is NOT called when collect=False
        # Note: We can't use capsys to capture Rust's direct stderr output,
        # so we verify the behavior by checking that the collection function is not called
        with patch("logust._logger._get_caller_info") as mock_caller:
            logger.info("Console test")
            mock_caller.assert_not_called()
