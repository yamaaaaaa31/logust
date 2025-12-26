"""Tests for callable sink support (logger.add(lambda msg: ...))."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from logust import Logger, LogLevel
from logust._logust import PyLogger


class TestLambdaSink:
    """Test lambda functions as sinks."""

    def test_lambda_receives_messages(self, tmp_path: Path) -> None:
        """Test that lambda sink receives log messages."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        logger.add(lambda msg: messages.append(msg))

        logger.info("Test message")

        assert len(messages) == 1
        assert "Test message" in messages[0]

    def test_lambda_receives_all_levels(self, tmp_path: Path) -> None:
        """Test that lambda receives messages at all levels."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        logger.add(lambda msg: messages.append(msg))

        logger.debug("Debug")
        logger.info("Info")
        logger.warning("Warning")
        logger.error("Error")

        assert len(messages) == 4

    def test_lambda_with_level_filter(self, tmp_path: Path) -> None:
        """Test that level filter works with lambda sink."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        logger.add(lambda msg: messages.append(msg), level="ERROR")

        logger.debug("Debug")
        logger.info("Info")
        logger.warning("Warning")
        logger.error("Error")
        logger.critical("Critical")

        # Only ERROR and CRITICAL should be captured
        assert len(messages) == 2
        assert any("Error" in m for m in messages)
        assert any("Critical" in m for m in messages)


class TestFunctionSink:
    """Test regular functions as sinks."""

    def test_function_receives_messages(self, tmp_path: Path) -> None:
        """Test that function sink receives log messages."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []

        def my_sink(msg: str) -> None:
            messages.append(msg)

        logger.add(my_sink)

        logger.info("Function sink test")

        assert len(messages) == 1
        assert "Function sink test" in messages[0]

    def test_function_with_format(self, tmp_path: Path) -> None:
        """Test that custom format works with function sink."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []

        def capture(msg: str) -> None:
            messages.append(msg)

        logger.add(capture, format="{level} - {message}")

        logger.info("Formatted message")

        assert len(messages) == 1
        assert "INFO" in messages[0]
        assert "Formatted message" in messages[0]


class TestCallableSinkRemoval:
    """Test removing callable sinks."""

    def test_remove_callable_sink(self, tmp_path: Path) -> None:
        """Test that callable sink can be removed.

        Note: Callable sinks use the callback mechanism internally,
        so they are removed via remove_callback().
        """
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        callback_id = logger.add(lambda msg: messages.append(msg))

        logger.info("Before removal")
        count_before = len(messages)

        # Callable sinks are internally implemented as callbacks
        logger.remove_callback(callback_id)

        logger.info("After removal")

        # Should not have received message after removal
        assert len(messages) == count_before


class TestCallableSinkWithSerialize:
    """Test callable sink with JSON serialization."""

    def test_callable_with_serialize(self, tmp_path: Path) -> None:
        """Test that serialize=True produces JSON output."""
        import json

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        logger.add(lambda msg: messages.append(msg), serialize=True)

        logger.info("JSON test")

        assert len(messages) == 1
        # Should be valid JSON
        data = json.loads(messages[0])
        assert data["message"] == "JSON test"
        assert data["level"] == "INFO"


class TestCallableSinkWithFilter:
    """Test callable sink with filter function."""

    def test_callable_with_custom_filter(self, tmp_path: Path) -> None:
        """Test that custom filter works with callable sink."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []

        def only_important(record: dict[str, Any]) -> bool:
            return "important" in record.get("message", "").lower()

        logger.add(lambda msg: messages.append(msg), filter=only_important)

        logger.info("Regular message")
        logger.info("IMPORTANT message")
        logger.info("Another regular")
        logger.info("Also important")

        # Only messages with "important" should be captured
        assert len(messages) == 2
        assert all("important" in m.lower() for m in messages)


class TestMultipleCallableSinks:
    """Test multiple callable sinks."""

    def test_multiple_callables(self, tmp_path: Path) -> None:
        """Test that multiple callable sinks all receive messages."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages1: list[str] = []
        messages2: list[str] = []

        logger.add(lambda msg: messages1.append(msg))
        logger.add(lambda msg: messages2.append(msg))

        logger.info("Multi-sink test")

        assert len(messages1) == 1
        assert len(messages2) == 1
        assert "Multi-sink test" in messages1[0]
        assert "Multi-sink test" in messages2[0]

    def test_callable_with_file_sink(self, tmp_path: Path) -> None:
        """Test callable sink alongside file sink."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        log_file = tmp_path / "mixed.log"

        logger.add(str(log_file))
        logger.add(lambda msg: messages.append(msg))

        logger.info("Mixed sink test")
        logger.complete()

        # Both should receive the message
        assert len(messages) == 1
        assert "Mixed sink test" in messages[0]

        content = log_file.read_text()
        assert "Mixed sink test" in content


class TestCallableSinkEdgeCases:
    """Test edge cases for callable sinks."""

    def test_callable_that_raises(self, tmp_path: Path) -> None:
        """Test that exception in callable doesn't crash logger."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        call_count = [0]

        def failing_sink(msg: str) -> None:
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("Intentional failure")

        logger.add(failing_sink)

        # Should not crash
        logger.info("First message")
        logger.info("Second message")

        # Both calls should have been attempted
        assert call_count[0] >= 1

    def test_class_method_as_sink(self, tmp_path: Path) -> None:
        """Test that class methods can be used as sinks."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        class LogCollector:
            def __init__(self) -> None:
                self.messages: list[str] = []

            def collect(self, msg: str) -> None:
                self.messages.append(msg)

        collector = LogCollector()
        logger.add(collector.collect)

        logger.info("Class method test")

        assert len(collector.messages) == 1
        assert "Class method test" in collector.messages[0]


class TestCallableSinkFormatTokens:
    """Test callable sink with new format tokens."""

    def test_callable_with_elapsed(self, tmp_path: Path) -> None:
        """Test that {elapsed} token works with callable sink."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        logger.add(lambda msg: messages.append(msg), format="{elapsed} | {message}")

        logger.info("Elapsed test")

        assert len(messages) == 1
        # elapsed format: HH:MM:SS.mmm
        import re

        assert re.match(r"\d{2}:\d{2}:\d{2}\.\d{3} \| Elapsed test", messages[0])

    def test_callable_with_thread(self, tmp_path: Path) -> None:
        """Test that {thread} token works with callable sink."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        logger.add(lambda msg: messages.append(msg), format="{thread} | {message}")

        logger.info("Thread test")

        assert len(messages) == 1
        # thread format: ThreadName:ID
        assert ":" in messages[0]
        assert "Thread test" in messages[0]

    def test_callable_with_process(self, tmp_path: Path) -> None:
        """Test that {process} token works with callable sink."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        logger.add(lambda msg: messages.append(msg), format="{process} | {message}")

        logger.info("Process test")

        assert len(messages) == 1
        # process format: ProcessName:ID
        assert ":" in messages[0]
        assert "Process test" in messages[0]

    def test_callable_with_file(self, tmp_path: Path) -> None:
        """Test that {file} token works with callable sink."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        logger.add(lambda msg: messages.append(msg), format="{file}:{line} | {message}")

        logger.info("File test")

        assert len(messages) == 1
        # file should be the test file name
        assert "test_callable_sink.py" in messages[0]
        assert "File test" in messages[0]

    def test_callable_with_extra(self, tmp_path: Path) -> None:
        """Test that {extra[key]} token works with callable sink."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        bound_logger = logger.bind(user="alice", request_id="12345")
        bound_logger.add(
            lambda msg: messages.append(msg),
            format="{extra[user]} - {extra[request_id]} | {message}",
        )

        bound_logger.info("Extra test")

        assert len(messages) == 1
        assert "alice" in messages[0]
        assert "12345" in messages[0]
        assert "Extra test" in messages[0]

    def test_message_containing_braces(self, tmp_path: Path) -> None:
        """Test that {level} etc in message are not replaced."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        logger.add(lambda msg: messages.append(msg), format="{level} | {message}")

        # Message contains literal {level} which should NOT be replaced
        logger.info("Error code: {level} is invalid")

        assert len(messages) == 1
        # The {level} in message should remain as-is, not become "INFO"
        assert "INFO | Error code: {level} is invalid" == messages[0]

    def test_message_with_spec_containing_braces(self, tmp_path: Path) -> None:
        """Test that {level} in message is preserved even with format spec."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        # Use {message:<50} with a format specifier
        logger.add(lambda msg: messages.append(msg), format="{level} | {message:<50}")

        # Message contains literal {level} which should NOT be replaced
        logger.info("Error: {level} happened")

        assert len(messages) == 1
        # The {level} in message should remain as-is, not become "INFO"
        # Message should be left-padded to 50 chars
        assert messages[0].startswith("INFO | Error: {level} happened")
        assert len(messages[0]) == len("INFO | ") + 50

    def test_callable_with_name_function(self, tmp_path: Path) -> None:
        """Test that {name} and {function} tokens work with callable sink."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        messages: list[str] = []
        logger.add(lambda msg: messages.append(msg), format="{name}:{function} | {message}")

        logger.info("Caller test")

        assert len(messages) == 1
        # Should contain function name
        assert "test_callable_with_name_function" in messages[0]
        assert "Caller test" in messages[0]
