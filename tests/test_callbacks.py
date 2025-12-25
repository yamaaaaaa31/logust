"""Tests for callbacks and catch decorator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger


class TestAddCallback:
    """Test add_callback() method."""

    def test_callback_receives_records(self, tmp_path: Path) -> None:
        """Test that callback receives log records."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        records: list[dict[str, Any]] = []

        def capture(record: dict[str, Any]) -> None:
            records.append(record.copy())

        logger.add_callback(capture)

        logger.info("Test message")

        assert len(records) >= 1
        record = records[-1]
        assert "message" in record or "level" in record

    def test_callback_with_level_filter(self, tmp_path: Path) -> None:
        """Test callback with level filter."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        records: list[dict[str, Any]] = []

        def capture(record: dict[str, Any]) -> None:
            records.append(record.copy())

        logger.add_callback(capture, level="ERROR")

        logger.debug("Debug message")
        logger.info("Info message")
        logger.error("Error message")

        assert len(records) >= 1
        messages = [r.get("message", "") for r in records]
        assert any("Error message" in m for m in messages)

    def test_multiple_callbacks(self, tmp_path: Path) -> None:
        """Test multiple callbacks."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        calls1: list[str] = []
        calls2: list[str] = []

        def callback1(record: dict[str, Any]) -> None:
            calls1.append(record.get("message", ""))

        def callback2(record: dict[str, Any]) -> None:
            calls2.append(record.get("message", ""))

        logger.add_callback(callback1)
        logger.add_callback(callback2)

        logger.info("Test")

        assert len(calls1) >= 1
        assert len(calls2) >= 1


class TestRemoveCallback:
    """Test remove_callback() method."""

    def test_remove_stops_calls(self, tmp_path: Path) -> None:
        """Test that removing callback stops it from receiving records."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        records: list[dict[str, Any]] = []

        def capture(record: dict[str, Any]) -> None:
            records.append(record.copy())

        callback_id = logger.add_callback(capture)

        logger.info("Before removal")
        count_before = len(records)

        logger.remove_callback(callback_id)

        logger.info("After removal")

        assert len(records) == count_before

    def test_remove_nonexistent(self) -> None:
        """Test removing non-existent callback returns False."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        result = logger.remove_callback(9999)
        assert result is False


class TestCatchDecorator:
    """Test @logger.catch() decorator."""

    def test_catch_logs_exception(self, tmp_path: Path) -> None:
        """Test that catch logs exceptions."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "catch.log"
        logger.add(str(log_file))

        @logger.catch(ValueError)
        def risky() -> None:
            raise ValueError("Expected error")

        risky()
        logger.complete()

        content = log_file.read_text()
        assert "ValueError" in content
        assert "Expected error" in content

    def test_catch_reraise(self, tmp_path: Path) -> None:
        """Test catch with reraise=True."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "reraise.log"
        logger.add(str(log_file))

        @logger.catch(ValueError, reraise=True)
        def risky() -> None:
            raise ValueError("Must reraise")

        with pytest.raises(ValueError, match="Must reraise"):
            risky()

        logger.complete()
        content = log_file.read_text()
        assert "ValueError" in content

    def test_catch_custom_level(self, tmp_path: Path) -> None:
        """Test catch with custom log level."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "level.log"
        logger.add(str(log_file))

        @logger.catch(Exception, level="WARNING")
        def risky() -> None:
            raise RuntimeError("Warning level")

        risky()
        logger.complete()

        content = log_file.read_text()
        assert "WARNING" in content

    def test_catch_custom_message(self, tmp_path: Path) -> None:
        """Test catch with custom message prefix."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "msg.log"
        logger.add(str(log_file))

        @logger.catch(Exception, message="Custom prefix")
        def risky() -> None:
            raise RuntimeError("Boom")

        risky()
        logger.complete()

        content = log_file.read_text()
        assert "Custom prefix" in content

    def test_catch_tuple_exceptions(self, tmp_path: Path) -> None:
        """Test catch with tuple of exception types."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "multi.log"
        logger.add(str(log_file))

        @logger.catch((ValueError, TypeError))
        def risky(flag: bool) -> None:
            if flag:
                raise ValueError("Value error")
            else:
                raise TypeError("Type error")

        risky(True)
        risky(False)
        logger.complete()

        content = log_file.read_text()
        assert "ValueError" in content
        assert "TypeError" in content

    def test_catch_preserves_return(self, tmp_path: Path) -> None:
        """Test that catch preserves return value on success."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        @logger.catch(Exception)
        def successful() -> str:
            return "success"

        result = successful()
        assert result == "success"

    def test_catch_uncaught_propagates(self, tmp_path: Path) -> None:
        """Test that uncaught exception types propagate."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        @logger.catch(ValueError)
        def risky() -> None:
            raise TypeError("Should propagate")

        with pytest.raises(TypeError, match="Should propagate"):
            risky()
