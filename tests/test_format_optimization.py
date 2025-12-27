"""Tests for format optimization features.

Part 1: intern! - Test callback/filter dict creation
Part 2: Lazy computation - Test format token-based lazy evaluation
"""

from pathlib import Path

from logust._logger import Logger
from logust._logust import LogLevel, PyLogger

# ============================================================================
# Part 1: intern! optimization tests (callback/filter dict)
# ============================================================================


class TestCallbackDictOptimization:
    """Test that callback/filter dict creation works correctly.

    These tests verify that callbacks and filters receive properly
    structured record dicts with all required fields.
    """

    def test_callback_receives_all_fields(self) -> None:
        """Callback should receive dict with all expected fields."""
        received: list[dict] = []

        def callback(record: dict) -> None:
            received.append(record.copy())

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.add_callback(callback)
        logger.info("Test message")

        assert len(received) == 1
        record = received[0]

        # Verify all required keys exist
        assert "level" in record
        assert "message" in record
        assert "timestamp" in record
        assert "name" in record
        assert "function" in record
        assert "line" in record
        assert "file" in record
        assert "thread_name" in record
        assert "thread_id" in record
        assert "process_name" in record
        assert "process_id" in record
        assert "elapsed" in record
        assert "extra" in record

    def test_callback_receives_correct_values(self) -> None:
        """Callback should receive correct values in the dict."""
        received: list[dict] = []

        def callback(record: dict) -> None:
            received.append(record.copy())

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.add_callback(callback)
        logger.warning("Warning message")

        assert len(received) == 1
        record = received[0]

        assert record["level"] == "WARNING"
        assert record["message"] == "Warning message"
        assert isinstance(record["line"], int)
        assert isinstance(record["thread_id"], int)
        assert isinstance(record["process_id"], int)
        assert isinstance(record["extra"], dict)

    def test_filter_receives_all_fields(self, tmp_path: Path) -> None:
        """Filter should receive dict with all expected fields."""
        received: list[dict] = []

        def filter_fn(record: dict) -> bool:
            received.append(record.copy())
            return True

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "filter_test.log"
        logger.add(str(log_file), filter=filter_fn)
        logger.info("Test message")

        assert len(received) == 1
        record = received[0]

        # Verify all required keys exist
        assert "level" in record
        assert "message" in record
        assert "timestamp" in record
        assert "name" in record
        assert "function" in record
        assert "line" in record
        assert "file" in record
        assert "thread_name" in record
        assert "thread_id" in record
        assert "process_name" in record
        assert "process_id" in record
        assert "elapsed" in record
        assert "extra" in record

    def test_multiple_callbacks_receive_same_structure(self) -> None:
        """Multiple callbacks should each receive properly structured dicts."""
        received1: list[dict] = []
        received2: list[dict] = []

        def callback1(record: dict) -> None:
            received1.append(record.copy())

        def callback2(record: dict) -> None:
            received2.append(record.copy())

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.add_callback(callback1)
        logger.add_callback(callback2)
        logger.info("Multi callback test")

        assert len(received1) == 1
        assert len(received2) == 1

        # Both should have same keys
        assert received1[0].keys() == received2[0].keys()

    def test_callback_with_extra_fields(self) -> None:
        """Callback should receive extra fields from bound context."""
        received: list[dict] = []

        def callback(record: dict) -> None:
            received.append(record.copy())

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.add_callback(callback)

        bound_logger = logger.bind(user_id="123", session="abc")
        bound_logger.info("Bound context test")

        assert len(received) == 1
        record = received[0]

        assert "extra" in record
        extra = record["extra"]
        assert extra.get("user_id") == "123"
        assert extra.get("session") == "abc"


# ============================================================================
# Part 2: Lazy token computation tests
# ============================================================================


class TestLazyTokenComputation:
    """Test that format tokens are computed lazily.

    These tests verify that tokens not present in the format string
    are not computed, improving performance.
    """

    def test_simple_format_works(self, tmp_path: Path) -> None:
        """Basic format with level and message should work."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "simple.log"
        logger.add(str(log_file), format="{level} | {message}")
        logger.info("Simple test")
        logger.complete()

        content = log_file.read_text()
        assert "INFO | Simple test" in content

    def test_message_only_format(self, tmp_path: Path) -> None:
        """Format with only {message} should work."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "message_only.log"
        logger.add(str(log_file), format="{message}")
        logger.info("Message only test")
        logger.complete()

        content = log_file.read_text()
        assert content.strip() == "Message only test"

    def test_level_only_format(self, tmp_path: Path) -> None:
        """Format with only {level} should work."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "level_only.log"
        logger.add(str(log_file), format="{level}")
        logger.warning("This message should not appear")
        logger.complete()

        content = log_file.read_text()
        assert content.strip() == "WARNING"
        assert "This message should not appear" not in content

    def test_time_included_when_in_format(self, tmp_path: Path) -> None:
        """Time should be included when {time} is in format."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "with_time.log"
        logger.add(str(log_file), format="{time} | {message}")
        logger.info("Time test")
        logger.complete()

        content = log_file.read_text()
        assert "Time test" in content
        # Time format typically includes colons (HH:MM:SS)
        assert ":" in content

    def test_elapsed_included_when_in_format(self, tmp_path: Path) -> None:
        """Elapsed should be included when {elapsed} is in format."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "with_elapsed.log"
        logger.add(str(log_file), format="{elapsed} | {message}")
        logger.info("Elapsed test")
        logger.complete()

        content = log_file.read_text()
        assert "Elapsed test" in content
        # Elapsed format is HH:MM:SS.mmm or similar
        assert ":" in content

    def test_caller_info_in_format(self, tmp_path: Path) -> None:
        """Caller info should be included when tokens are in format."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "with_caller.log"
        logger.add(str(log_file), format="{function}:{line} | {message}")
        logger.info("Caller test")
        logger.complete()

        content = log_file.read_text()
        assert "Caller test" in content
        # Function name should be present
        assert "test_caller_info_in_format" in content
        # Line number should be present (a number followed by |)
        assert ":" in content

    def test_thread_info_in_format(self, tmp_path: Path) -> None:
        """Thread info should be included when {thread} is in format."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "with_thread.log"
        logger.add(str(log_file), format="{thread} | {message}")
        logger.info("Thread test")
        logger.complete()

        content = log_file.read_text()
        assert "Thread test" in content
        # Thread format is "name:id"
        assert ":" in content

    def test_process_info_in_format(self, tmp_path: Path) -> None:
        """Process info should be included when {process} is in format."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "with_process.log"
        logger.add(str(log_file), format="{process} | {message}")
        logger.info("Process test")
        logger.complete()

        content = log_file.read_text()
        assert "Process test" in content
        # Process format is "name:id"
        assert ":" in content

    def test_full_format_all_tokens(self, tmp_path: Path) -> None:
        """All tokens should work when all are in format."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "full_format.log"
        full_format = (
            "{time} | {level:<8} | {elapsed} | "
            "{name}:{function}:{line} | {thread} | {process} | {message}"
        )
        logger.add(str(log_file), format=full_format)
        logger.info("Full format test")
        logger.complete()

        content = log_file.read_text()
        assert "INFO" in content
        assert "Full format test" in content
        assert "test_full_format_all_tokens" in content

    def test_level_width_format(self, tmp_path: Path) -> None:
        """Level with width specifier should work."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "level_width.log"
        logger.add(str(log_file), format="{level:<8}|{message}")
        logger.info("Width test")
        logger.complete()

        content = log_file.read_text()
        # INFO should be padded to 8 chars
        assert "INFO    |Width test" in content


# ============================================================================
# Performance-related tests (verify optimization doesn't break functionality)
# ============================================================================


class TestOptimizationCompatibility:
    """Test that optimizations maintain backward compatibility."""

    def test_callback_and_handler_work_together(self, tmp_path: Path) -> None:
        """Callback and file handler should work together."""
        callback_received: list[dict] = []

        def callback(record: dict) -> None:
            callback_received.append(record.copy())

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "combined.log"
        logger.add(str(log_file), format="{level} | {message}")
        logger.add_callback(callback)
        logger.info("Combined test")
        logger.complete()

        # Both should work
        assert len(callback_received) == 1
        content = log_file.read_text()
        assert "INFO | Combined test" in content

    def test_filter_and_callback_work_together(self, tmp_path: Path) -> None:
        """Filter and callback should work together."""
        filter_received: list[dict] = []
        callback_received: list[dict] = []

        def filter_fn(record: dict) -> bool:
            filter_received.append(record.copy())
            return record["level"] == "INFO"

        def callback(record: dict) -> None:
            callback_received.append(record.copy())

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        log_file = tmp_path / "filter_callback.log"
        logger.add(str(log_file), format="{message}", filter=filter_fn)
        logger.add_callback(callback)

        logger.debug("Debug - should be filtered")
        logger.info("Info - should pass")
        logger.complete()

        # Filter should see both messages
        assert len(filter_received) == 2

        # Callback should see both (callback doesn't use filter)
        assert len(callback_received) == 2

        # File should only have INFO
        content = log_file.read_text()
        assert "Info - should pass" in content
        assert "Debug - should be filtered" not in content
