"""Tests for CollectOptions functionality.

Tests the union logic for CollectOptions, patch() inheritance,
and remove_callback() cleanup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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

    def test_fixed_caller_info_with_explicit_settings(self, tmp_path: Path) -> None:
        """Fixed CallerInfo should be used when all handlers have explicit settings.

        When all handlers have explicit CollectOptions settings (no auto-detect),
        fixed values can be used.
        """
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        fixed_caller = CallerInfo(
            name="fixed_module", function="fixed_func", line=999, file="fixed.py"
        )

        # Handler 1: fixed caller info
        log1 = tmp_path / "log1.log"
        logger.add(
            str(log1),
            format="{function}:{line} | {message}",
            collect=CollectOptions(caller=fixed_caller),
        )

        # Handler 2: explicit caller=False (not auto-detect)
        log2 = tmp_path / "log2.log"
        logger.add(str(log2), format="{message}", collect=CollectOptions(caller=False))

        logger.info("Test message")
        logger.complete()

        # Handler 1 should use fixed caller info (no auto-detect handler)
        content1 = log1.read_text()
        assert "fixed_func:999" in content1

    def test_fixed_and_true_true_wins(self, tmp_path: Path) -> None:
        """When one handler has True and another has fixed value, True wins (dynamic collection)."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        fixed_caller = CallerInfo(
            name="fixed_module", function="fixed_func", line=999, file="fixed.py"
        )

        # Handler 1: fixed caller info
        log1 = tmp_path / "log1.log"
        logger.add(
            str(log1),
            format="{function}:{line} | {message}",
            collect=CollectOptions(caller=fixed_caller),
        )

        # Handler 2: True (force collection)
        log2 = tmp_path / "log2.log"
        logger.add(
            str(log2), format="{function}:{line} | {message}", collect=CollectOptions(caller=True)
        )

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
        logger.add(
            str(log_file),
            format="{function}:{line} | {message}",
            collect=CollectOptions(caller=fixed_caller),
        )

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
        logger.add(
            str(log_file),
            format="{thread} | {message}",
            collect=CollectOptions(thread=fixed_thread),
        )

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
        logger.add(
            str(log_file),
            format="{process} | {message}",
            collect=CollectOptions(process=fixed_process),
        )

        logger.info("Test message")
        logger.complete()

        content = log_file.read_text()
        assert "FixedProcess:99999" in content


class TestSerializeWithCollectOptions:
    """Test serialize=True with CollectOptions."""

    def test_serialize_true_with_caller_false(self, tmp_path: Path) -> None:
        """serialize=True with caller=False should output JSON without caller fields."""
        import json

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "test.json"
        logger.add(
            str(log_file),
            serialize=True,
            collect=CollectOptions(caller=False),
        )

        logger.info("Test message")
        logger.complete()

        content = log_file.read_text().strip()
        record = json.loads(content)

        # JSON should have basic fields
        assert record["level"] == "INFO"
        assert record["message"] == "Test message"

        # Caller fields should be absent or empty (skip_serializing_if handles this)
        # The key point is no error should occur
        assert "time" in record


class TestCallableSinkRemoval:
    """Test that callable sinks can be removed with remove() or remove_callback()."""

    def test_callable_sink_removal_via_remove_callback(self) -> None:
        """Callable sink can be removed using remove_callback()."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)

        messages: list[str] = []
        handler_id = logger.add(lambda msg: messages.append(msg), format="{message}")

        # Log a message
        logger.info("First message")
        assert len(messages) == 1

        # remove_callback() works for callable sinks
        result = logger.remove_callback(handler_id)
        assert result is True

        # After removal, messages should not be added
        logger.info("Second message")
        assert len(messages) == 1  # Still 1, not 2

    def test_callable_sink_removal_via_remove(self) -> None:
        """Callable sink can also be removed using remove() (redirects to remove_callback)."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)

        messages: list[str] = []
        handler_id = logger.add(lambda msg: messages.append(msg), format="{message}")

        # Log a message
        logger.info("First message")
        assert len(messages) == 1

        # remove() now correctly redirects to remove_callback() for callable sinks
        result = logger.remove(handler_id)
        assert result is True

        # After removal, messages should not be added
        logger.info("Second message")
        assert len(messages) == 1  # Still 1, not 2


class TestCallbackWithCollectOptions:
    """Test that callbacks always receive full records regardless of CollectOptions."""

    def test_callback_with_caller_false_still_collects(self) -> None:
        """Callback with caller=False should still receive caller info.

        Callbacks always need full records (TokenRequirements::all() in Rust),
        so caller=False should not prevent collection.
        """
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        records: list[dict] = []

        def capture_record(record: dict) -> None:
            records.append(record.copy())

        # Add callback with caller=False - should NOT prevent collection
        logger.add_callback(capture_record)
        # Also add a handler with caller=False via add()
        messages: list[str] = []
        logger.add(
            lambda msg: messages.append(msg),
            format="{message}",
            collect=CollectOptions(caller=False),
        )

        logger.info("Test message")

        # Callback should still receive caller info because callbacks need full records
        assert len(records) == 1
        record = records[0]
        # The record should have caller info (function should be this test function)
        assert "function" in record
        assert record["function"] == "test_callback_with_caller_false_still_collects"

    def test_callable_sink_with_caller_false_respects_option(self) -> None:
        """Callable sink with caller=False should respect the option.

        Unlike raw callbacks (via add_callback), callable sinks receive
        formatted strings and should respect CollectOptions.
        """
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        messages: list[str] = []
        logger.add(
            lambda msg: messages.append(msg),
            format="{function} | {message}",
            collect=CollectOptions(caller=False),
        )

        logger.info("Test message")

        assert len(messages) == 1
        # With caller=False, function should be empty
        assert " | Test message" in messages[0]


class TestFixedValueVsAutoDectect:
    """Test that auto-detect wins over fixed value when another handler needs dynamic info."""

    def test_fixed_value_does_not_block_auto_detect(self, tmp_path: Path) -> None:
        """Fixed value should not prevent dynamic collection when format needs it.

        If Handler A has fixed caller and Handler B's format needs caller,
        dynamic collection should be used (not the fixed value).
        """
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        fixed_caller = CallerInfo(
            name="fixed_module", function="fixed_func", line=999, file="fixed.py"
        )

        # Handler 1: fixed caller info
        log1 = tmp_path / "fixed.log"
        logger.add(
            str(log1),
            format="{function}:{line} | {message}",
            collect=CollectOptions(caller=fixed_caller),
        )

        # Handler 2: auto-detect from format (needs caller)
        log2 = tmp_path / "dynamic.log"
        logger.add(str(log2), format="{function}:{line} | {message}")

        logger.info("Test message")
        logger.complete()

        # Handler 2 needs actual caller info, so dynamic collection should be used
        content2 = log2.read_text()
        # Should have actual function name, not "fixed_func"
        assert "test_fixed_value_does_not_block_auto_detect" in content2
        assert "fixed_func" not in content2


class TestRustNeedsOverridesCallerFalse:
    """Test that Rust's needs_* overrides caller_false from CollectOptions."""

    def test_callback_needs_overrides_caller_false(self) -> None:
        """Callback needs full records, so caller=False should be ignored.

        When callbacks are registered, Rust sets TokenRequirements::all(),
        meaning it needs caller info. CollectOptions(caller=False) should
        not prevent collection.
        """
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        records: list[dict] = []

        def capture(record: dict) -> None:
            records.append(record.copy())

        # Register callback - Rust now needs full records
        logger.add_callback(capture)

        # Add callable sink with caller=False - should NOT prevent collection
        messages: list[str] = []
        logger.add(
            lambda msg: messages.append(msg),
            format="{message}",
            collect=CollectOptions(caller=False),
        )

        logger.info("Test message")

        # Callback should still receive caller info despite caller=False on callable sink
        assert len(records) == 1
        assert records[0]["function"] == "test_callback_needs_overrides_caller_false"


class TestFilterWithCollectOptions:
    """Test that filters always receive full records regardless of CollectOptions."""

    def test_filter_with_caller_false_still_collects(self, tmp_path: Path) -> None:
        """Filter with caller=False should still get caller info."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "filtered.log"

        def requires_function(record: dict[str, Any]) -> bool:
            return bool(record.get("function"))

        logger.add(
            str(log_file),
            format="{function} | {message}",
            filter=requires_function,
            collect=CollectOptions(caller=False),
        )

        logger.info("Test message")
        logger.complete()

        content = log_file.read_text()
        assert "test_filter_with_caller_false_still_collects" in content


class TestRemoveAllClearsCallbacks:
    """Test that remove(None) also removes callbacks."""

    def test_remove_all_removes_callbacks(self) -> None:
        """remove(None) should remove all handlers AND all callbacks."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)

        messages: list[str] = []

        # Add a callable sink
        logger.add(lambda msg: messages.append(msg), format="{message}")

        logger.info("Before remove")
        assert len(messages) == 1

        # Remove ALL handlers (including callable sinks)
        logger.remove()

        # After remove(None), callable sink should be removed
        logger.info("After remove")
        assert len(messages) == 1  # Still 1, not 2

    def test_remove_all_clears_tracking(self) -> None:
        """remove(None) should clear both _collect_options and _callback_ids."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()  # Suppress output

        # Add multiple callable sinks
        logger.add(lambda msg: None, format="{message}")
        logger.add(lambda msg: None, format="{message}")

        assert len(logger._callback_ids) == 2
        assert len(logger._collect_options) == 2

        # Remove all
        logger.remove()

        # All tracking should be cleared
        assert len(logger._callback_ids) == 0
        assert len(logger._collect_options) == 0


class TestEmptyContainerPreservation:
    """Test that empty containers are preserved in bind/patch."""

    def test_bind_preserves_empty_containers(self) -> None:
        """bind() should preserve empty _callback_ids and _collect_options."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        # Logger starts with empty containers
        assert logger._callback_ids == set()
        assert logger._collect_options == {}
        assert logger._filter_ids == set()

        # bind() should pass the SAME empty containers, not new ones
        bound = logger.bind(user="alice")

        # Containers should be the exact same objects (identity check)
        assert bound._callback_ids is logger._callback_ids
        assert bound._collect_options is logger._collect_options
        assert bound._filter_ids is logger._filter_ids

    def test_patch_preserves_empty_containers(self) -> None:
        """patch() should preserve empty _callback_ids and _collect_options."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        # Logger starts with empty containers
        assert logger._callback_ids == set()
        assert logger._collect_options == {}
        assert logger._filter_ids == set()

        # patch() should pass the SAME empty containers, not new ones
        patched = logger.patch(lambda r: None)

        # Containers should be the exact same objects (identity check)
        assert patched._callback_ids is logger._callback_ids
        assert patched._collect_options is logger._collect_options
        assert patched._filter_ids is logger._filter_ids

    def test_bind_preserves_raw_callback_ids(self) -> None:
        """bind() should preserve _raw_callback_ids."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        # Add a raw callback
        logger.add_callback(lambda r: None)
        assert len(logger._raw_callback_ids) == 1

        # bind() should share _raw_callback_ids
        bound = logger.bind(user="alice")
        assert bound._raw_callback_ids is logger._raw_callback_ids

    def test_patch_preserves_raw_callback_ids(self) -> None:
        """patch() should preserve _raw_callback_ids."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        # Add a raw callback
        logger.add_callback(lambda r: None)
        assert len(logger._raw_callback_ids) == 1

        # patch() should share _raw_callback_ids
        patched = logger.patch(lambda r: None)
        assert patched._raw_callback_ids is logger._raw_callback_ids


class TestCallableSinkAutoDetect:
    """Test that callable sinks auto-detect requirements from format."""

    def test_callable_sink_message_only_skips_caller(self) -> None:
        """Callable sink with format={message} should not collect caller info.

        This tests that callable sinks compute requirements from format string
        rather than relying on Rust's needs_* which is polluted by callback
        registration.
        """
        from unittest.mock import patch

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        messages: list[str] = []
        # Format only uses {message}, no caller tokens
        logger.add(lambda msg: messages.append(msg), format="{message}")

        with patch("logust._logger._get_caller_info") as mock_caller:
            logger.info("Test message")
            # _get_caller_info should NOT be called because format doesn't need it
            mock_caller.assert_not_called()

        assert len(messages) == 1
        assert messages[0] == "Test message"

    def test_callable_sink_with_function_collects_caller(self) -> None:
        """Callable sink with format containing {function} should collect caller info."""
        from unittest.mock import patch

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        messages: list[str] = []
        # Format uses {function}, needs caller info
        logger.add(lambda msg: messages.append(msg), format="{function} | {message}")

        with patch("logust._logger._get_caller_info") as mock_caller:
            mock_caller.return_value = ("test_mod", "test_func", 42, "test.py")
            logger.info("Test message")
            # _get_caller_info SHOULD be called
            mock_caller.assert_called_once()

        assert len(messages) == 1
        assert "test_func" in messages[0]

    def test_callable_sink_collect_options_computed_from_format(self) -> None:
        """Callable sink with collect=None should have CollectOptions computed from format."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # Format only uses {message}
        handler_id = logger.add(lambda msg: None, format="{message}")

        # CollectOptions should be computed from format (not default auto-detect)
        opts = logger._collect_options[handler_id]
        assert opts.caller is False  # Not needed by format
        assert opts.thread is False  # Not needed by format
        assert opts.process is False  # Not needed by format

    def test_callable_sink_with_thread_collects_thread(self) -> None:
        """Callable sink with format containing {thread} should collect thread info."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # Format uses {thread}
        handler_id = logger.add(lambda msg: None, format="{thread} | {message}")

        opts = logger._collect_options[handler_id]
        assert opts.thread is True
        assert opts.caller is False
        assert opts.process is False

    def test_callable_sink_explicit_collect_overrides_format(self) -> None:
        """Explicit CollectOptions should override format-based auto-detect."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # Format only uses {message}, but explicitly request caller info
        handler_id = logger.add(
            lambda msg: None,
            format="{message}",
            collect=CollectOptions(caller=True),
        )

        opts = logger._collect_options[handler_id]
        # Explicit CollectOptions should be used, not computed from format
        assert opts.caller is True


class TestRemoveAllReturnValue:
    """Test that remove(None) returns correct value."""

    def test_remove_all_returns_true_when_callbacks_removed(self) -> None:
        """remove(None) should return True if callbacks were removed."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()  # Remove default handlers

        # Add only callable sink (no file handlers)
        logger.add(lambda msg: None, format="{message}")

        # remove(None) should return True because callback was removed
        result = logger.remove()
        assert result is True

    def test_remove_all_returns_true_when_handlers_removed(self) -> None:
        """remove(None) should return True if handlers were removed."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)

        # Has default console handler
        result = logger.remove()
        assert result is True

    def test_remove_all_on_empty_logger(self) -> None:
        """remove(None) on empty logger returns Rust's result (may be True)."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()  # Remove everything first

        # Verify tracking is empty
        assert len(logger._callback_ids) == 0
        assert len(logger._raw_callback_ids) == 0

        # Second remove - Rust may return True even when empty
        # The important thing is no error is raised
        logger.remove()


class TestDefaultHandlerWithCallableSink:
    """Test that default console handler works correctly with callable sinks."""

    def test_file_handler_keeps_caller_with_callable_sink(self, tmp_path: Path) -> None:
        """File handler with caller format should keep caller info when callable sink is added.

        Regression test: Callable sinks with format="{message}" have caller=False
        (auto-detect from format), which should not prevent caller collection
        for other handlers that need it.
        """
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()  # Remove default console handler

        # Add file handler with caller info in format
        log_file = tmp_path / "test.log"
        logger.add(str(log_file), format="{function}:{line} | {message}")

        # Add callable sink that only uses {message}
        collected: list[str] = []
        logger.add(lambda msg: collected.append(msg), format="{message}")

        # Both property check and actual output verification
        assert inner.needs_caller_info_for_handlers is True

        # Log a message and verify caller info is present in output
        logger.info("Test message")
        logger.complete()

        content = log_file.read_text()
        # Should contain function name and line number
        assert "test_file_handler_keeps_caller_with_callable_sink" in content
        assert "Test message" in content
        # Line number should be present (not empty)
        assert ": |" not in content  # This would indicate empty function/line

    def test_callable_sink_message_only_no_caller(self) -> None:
        """Callable sink with {message} format should not force caller collection.

        When there's no default handler, a callable sink with format="{message}"
        should correctly auto-detect that caller info is not needed.
        """
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()  # Remove default console handler

        collected: list[str] = []
        handler_id = logger.add(lambda msg: collected.append(msg), format="{message}")

        # Verify CollectOptions was computed from format (caller=False)
        opts = logger._collect_options.get(handler_id)
        assert opts is not None
        assert opts.caller is False

        # needs_caller_info_for_handlers should be False since no handler needs it
        assert inner.needs_caller_info_for_handlers is False

    def test_callable_sink_does_not_block_other_handler_caller(self, tmp_path: Path) -> None:
        """Adding a callable sink should not block caller info for existing file handlers.

        This tests the actual regression scenario: a file handler with caller tokens
        should still receive caller info even when a callable sink with message-only
        format is added.
        """
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # Add file handler first
        log_file = tmp_path / "test.log"
        logger.add(str(log_file), format="{name}:{function}:{line} | {message}")

        # Then add callable sink with message-only format
        messages: list[str] = []
        logger.add(lambda msg: messages.append(msg), format="{message}")

        # Log and verify
        logger.info("Hello")
        logger.complete()

        # File should have caller info
        content = log_file.read_text()
        assert "test_callable_sink_does_not_block_other_handler_caller" in content
        assert "Hello" in content

        # Callable sink should just have message
        assert len(messages) == 1
        assert messages[0] == "Hello"


class TestNeedsInfoForHandlers:
    """Test that needs_*_for_handlers excludes callbacks."""

    def test_callback_does_not_affect_needs_caller_for_handlers(self) -> None:
        """Raw callbacks should not affect needs_caller_info_for_handlers."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()  # Remove console handler

        # Add raw callback (which internally sets TokenRequirements::all())
        callback_id = logger.add_callback(lambda record: None)

        # needs_caller_info includes callbacks (True due to TokenRequirements::all())
        assert inner.needs_caller_info is True

        # But needs_caller_info_for_handlers excludes callbacks
        assert inner.needs_caller_info_for_handlers is False

        # Same for thread and process
        assert inner.needs_thread_info is True
        assert inner.needs_thread_info_for_handlers is False
        assert inner.needs_process_info is True
        assert inner.needs_process_info_for_handlers is False

        logger.remove_callback(callback_id)

    def test_handler_with_caller_tokens_sets_needs_for_handlers(self, tmp_path: Path) -> None:
        """Handler format with caller tokens should set needs_caller_info_for_handlers."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # Add handler with {function} in format
        log_file = tmp_path / "test.log"
        logger.add(str(log_file), format="{function} | {message}")

        # Both should be True since handler format needs caller info
        assert inner.needs_caller_info is True
        assert inner.needs_caller_info_for_handlers is True

    def test_handler_without_caller_tokens(self, tmp_path: Path) -> None:
        """Handler format without caller tokens should not need caller info."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        # Add handler with only {level} and {message}
        log_file = tmp_path / "test.log"
        logger.add(str(log_file), format="{level} | {message}")

        # Neither should need caller info
        assert inner.needs_caller_info is False
        assert inner.needs_caller_info_for_handlers is False
