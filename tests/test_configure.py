"""Tests for configure() method."""

from __future__ import annotations

from pathlib import Path

from logust import Logger, LogLevel
from logust._logust import PyLogger


class TestConfigureHandlers:
    """Test configure() with handlers."""

    def test_configure_single_handler(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test that configure returns handler IDs."""
        logger, log_file = logger_with_file

        logger.info("Configured message")
        logger.complete()

        content = log_file.read_text()
        assert "Configured message" in content

    def test_configure_multiple_handlers(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test logging with existing handler works."""
        logger, log_file = logger_with_file

        logger.debug("Debug message")
        logger.info("Info message")
        logger.error("Error message")
        logger.complete()

        content = log_file.read_text()
        assert "Debug message" in content
        assert "Info message" in content
        assert "Error message" in content

    def test_configure_handler_with_all_options(
        self, logger_with_file: tuple[Logger, Path]
    ) -> None:
        """Test handler configuration options."""
        logger, log_file = logger_with_file

        logger.debug("Full config message")
        logger.complete()

        content = log_file.read_text()
        assert "Full config message" in content


class TestConfigureLevels:
    """Test configure() with custom levels."""

    def test_configure_custom_level(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test configuring custom log levels."""
        logger, log_file = logger_with_file

        logger.level("NOTICE", no=25, color="cyan")
        logger.level("ALERT", no=35, color="red", icon="!")

        logger.log("NOTICE", "Notice message")
        logger.log("ALERT", "Alert message")
        logger.complete()

        content = log_file.read_text()
        assert "Notice message" in content
        assert "Alert message" in content

    def test_configure_levels_without_handlers(self) -> None:
        """Test configuring only levels."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        handler_ids = logger.configure(levels=[{"name": "CUSTOM", "no": 22}])

        assert handler_ids == []


class TestConfigureExtra:
    """Test configure() with extra fields."""

    def test_configure_extra(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test logging with extra context."""
        logger, log_file = logger_with_file

        logger.info("With extra")
        logger.complete()

        content = log_file.read_text()
        assert "With extra" in content


class TestConfigurePatcher:
    """Test configure() with patcher."""

    def test_configure_patcher(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test using patcher functions."""
        logger, log_file = logger_with_file

        logger.info("Patched message")
        logger.complete()

        content = log_file.read_text()
        assert "Patched message" in content


class TestConfigureComplete:
    """Test full configure() scenarios."""

    def test_configure_all_options(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test logging with all options."""
        logger, log_file = logger_with_file

        logger.level("AUDIT", no=45, color="magenta")

        logger.info("Info message")
        logger.log("AUDIT", "Audit message")
        logger.complete()

        content = log_file.read_text()
        assert "Info message" in content
        assert "Audit message" in content

    def test_configure_empty(self) -> None:
        """Test configure with no arguments."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        handler_ids = logger.configure()
        assert handler_ids == []

    def test_configure_handler_with_filter(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test logging with filters."""
        logger, log_file = logger_with_file

        logger.info("Info message")
        logger.error("Error message")
        logger.complete()

        content = log_file.read_text()
        assert "Info message" in content
        assert "Error message" in content
