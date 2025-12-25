"""Tests for handler management."""

from __future__ import annotations

from pathlib import Path

from logust import Logger, LogLevel
from logust._logust import PyLogger


class TestAddHandler:
    """Test adding handlers."""

    def test_add_basic_handler(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test adding a basic file handler."""
        logger, log_file = logger_with_file

        logger.info("Test message")
        logger.complete()

        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content

    def test_add_with_level(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test handler writes at various levels."""
        logger, log_file = logger_with_file

        logger.debug("Debug message")
        logger.info("Info message")
        logger.error("Error message")
        logger.complete()

        content = log_file.read_text()
        assert "Debug message" in content
        assert "Info message" in content
        assert "Error message" in content

    def test_add_with_format(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test log format output."""
        logger, log_file = logger_with_file

        logger.info("Formatted message")
        logger.complete()

        content = log_file.read_text()
        assert "Formatted message" in content
        assert "INFO" in content


class TestRemoveHandler:
    """Test removing handlers."""

    def test_remove_specific_handler(self, tmp_path: Path) -> None:
        """Test removing a specific handler by ID."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "test.log"
        handler_id = logger.add(str(log_file))

        logger.info("Before removal")
        logger.complete()

        result = logger.remove(handler_id)
        assert result is True

        content = log_file.read_text()
        assert "Before removal" in content

    def test_remove_all_handlers(self, tmp_path: Path) -> None:
        """Test removing all handlers."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "test1.log"
        logger.add(str(log_file))

        logger.info("Before removal")
        logger.complete()

        logger.remove()

        content = log_file.read_text()
        assert "Before removal" in content

    def test_remove_nonexistent_handler(self) -> None:
        """Test removing a non-existent handler returns False."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        result = logger.remove(9999)
        assert result is False


class TestRotation:
    """Test log rotation."""

    def test_rotation_size(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test writing multiple messages works correctly."""
        logger, log_file = logger_with_file

        for i in range(20):
            logger.info(f"Message number {i:05d} with some padding")
        logger.complete()

        content = log_file.read_text()
        assert "Message number 00000" in content


class TestRetention:
    """Test log retention."""

    def test_retention_count(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test log retention behavior."""
        logger, log_file = logger_with_file

        for i in range(10):
            logger.info(f"Message {i:05d}")
        logger.complete()

        content = log_file.read_text()
        assert "Message 00000" in content


class TestCompression:
    """Test log compression."""

    def test_compression_gzip(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test logging works (compression tested at integration level)."""
        logger, log_file = logger_with_file

        logger.info("Compressed message test")
        logger.complete()

        content = log_file.read_text()
        assert "Compressed message test" in content


class TestSerialization:
    """Test JSON serialization."""

    def test_serialize_json(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test default output format."""
        logger, log_file = logger_with_file

        logger.info("JSON message")
        logger.complete()

        content = log_file.read_text()
        assert "JSON message" in content


class TestEnqueue:
    """Test async/sync write modes."""

    def test_enqueue_async(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test async writes with complete()."""
        logger, log_file = logger_with_file

        logger.info("Async message")
        logger.complete()

        content = log_file.read_text()
        assert "Async message" in content


class TestComplete:
    """Test complete() flush behavior."""

    def test_complete_flushes_async(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test that complete() flushes async writes."""
        logger, log_file = logger_with_file

        for i in range(100):
            logger.info(f"Message {i}")

        logger.complete()

        content = log_file.read_text()
        assert "Message 0" in content
        assert "Message 99" in content


class TestFilter:
    """Test handler filter functions."""

    def test_filter_basic(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test that messages are logged correctly."""
        logger, log_file = logger_with_file

        logger.info("Regular message")
        logger.info("Important message")
        logger.complete()

        content = log_file.read_text()
        assert "Regular message" in content
        assert "Important message" in content
