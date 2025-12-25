"""Tests for basic logger functionality."""

from __future__ import annotations

from pathlib import Path

from logust import Logger


class TestLogLevels:
    """Test all log level methods."""

    def test_trace(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test TRACE level logging."""
        logger, log_file = logger_with_file
        logger.trace("Trace message")
        logger.complete()

        content = log_file.read_text()
        assert "TRACE" in content
        assert "Trace message" in content

    def test_debug(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test DEBUG level logging."""
        logger, log_file = logger_with_file
        logger.debug("Debug message")
        logger.complete()

        content = log_file.read_text()
        assert "DEBUG" in content
        assert "Debug message" in content

    def test_info(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test INFO level logging."""
        logger, log_file = logger_with_file
        logger.info("Info message")
        logger.complete()

        content = log_file.read_text()
        assert "INFO" in content
        assert "Info message" in content

    def test_success(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test SUCCESS level logging."""
        logger, log_file = logger_with_file
        logger.success("Success message")
        logger.complete()

        content = log_file.read_text()
        assert "SUCCESS" in content
        assert "Success message" in content

    def test_warning(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test WARNING level logging."""
        logger, log_file = logger_with_file
        logger.warning("Warning message")
        logger.complete()

        content = log_file.read_text()
        assert "WARNING" in content
        assert "Warning message" in content

    def test_error(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test ERROR level logging."""
        logger, log_file = logger_with_file
        logger.error("Error message")
        logger.complete()

        content = log_file.read_text()
        assert "ERROR" in content
        assert "Error message" in content

    def test_fail(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test FAIL level logging."""
        logger, log_file = logger_with_file
        logger.fail("Fail message")
        logger.complete()

        content = log_file.read_text()
        assert "FAIL" in content
        assert "Fail message" in content

    def test_critical(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test CRITICAL level logging."""
        logger, log_file = logger_with_file
        logger.critical("Critical message")
        logger.complete()

        content = log_file.read_text()
        assert "CRITICAL" in content
        assert "Critical message" in content


class TestException:
    """Test exception logging."""

    def test_exception_in_except_block(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test exception() captures traceback in except block."""
        logger, log_file = logger_with_file

        try:
            raise ValueError("Test error")
        except ValueError:
            logger.exception("An error occurred")

        logger.complete()
        content = log_file.read_text()

        assert "ERROR" in content
        assert "An error occurred" in content
        assert "ValueError" in content
        assert "Test error" in content

    def test_exception_outside_except_block(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test exception() without active exception logs plain error."""
        logger, log_file = logger_with_file

        logger.exception("No exception here")
        logger.complete()

        content = log_file.read_text()
        assert "ERROR" in content
        assert "No exception here" in content


class TestGenericLog:
    """Test generic log() method."""

    def test_log_with_string_level(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test log() with string level name."""
        logger, log_file = logger_with_file
        logger.log("INFO", "Generic info message")
        logger.complete()

        content = log_file.read_text()
        assert "INFO" in content
        assert "Generic info message" in content

    def test_log_with_numeric_level(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test log() with numeric level."""
        logger, log_file = logger_with_file
        logger.log(20, "Level 20 message")
        logger.complete()

        content = log_file.read_text()
        assert "INFO" in content
        assert "Level 20 message" in content

    def test_log_with_exception(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test log() with exception parameter."""
        logger, log_file = logger_with_file
        logger.log("ERROR", "Error with trace", exception="Traceback here")
        logger.complete()

        content = log_file.read_text()
        assert "ERROR" in content
        assert "Error with trace" in content
        assert "Traceback here" in content
