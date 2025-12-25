"""Tests for log levels and custom levels."""

from __future__ import annotations

from pathlib import Path

from logust import Logger, LogLevel
from logust._logust import PyLogger


class TestBuiltinLevels:
    """Test built-in log levels."""

    def test_level_order(self) -> None:
        """Test that levels are ordered correctly."""
        assert LogLevel.Trace.value < LogLevel.Debug.value
        assert LogLevel.Debug.value < LogLevel.Info.value
        assert LogLevel.Info.value < LogLevel.Success.value
        assert LogLevel.Success.value < LogLevel.Warning.value
        assert LogLevel.Warning.value < LogLevel.Error.value
        assert LogLevel.Error.value < LogLevel.Fail.value
        assert LogLevel.Fail.value < LogLevel.Critical.value

    def test_level_values(self) -> None:
        """Test specific level values."""
        assert LogLevel.Trace.value == 5
        assert LogLevel.Debug.value == 10
        assert LogLevel.Info.value == 20
        assert LogLevel.Success.value == 25
        assert LogLevel.Warning.value == 30
        assert LogLevel.Error.value == 40
        assert LogLevel.Fail.value == 45
        assert LogLevel.Critical.value == 50


class TestCustomLevels:
    """Test custom log level registration."""

    def test_register_custom_level(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test registering and using a custom level."""
        logger, log_file = logger_with_file

        logger.level("NOTICE", no=25, color="cyan")

        logger.log("NOTICE", "Custom notice message")
        logger.complete()

        content = log_file.read_text()
        assert "Custom notice message" in content

    def test_custom_level_with_icon(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test custom level with icon."""
        logger, log_file = logger_with_file

        logger.level("ALERT", no=35, color="red", icon="!")
        logger.log("ALERT", "Alert message")
        logger.complete()

        content = log_file.read_text()
        assert "Alert message" in content


class TestSetGetLevel:
    """Test set_level and get_level methods."""

    def test_get_level_initial(self) -> None:
        """Test getting initial level."""
        inner = PyLogger(LogLevel.Info)
        logger = Logger(inner)

        level = logger.get_level()
        assert level.value <= LogLevel.Info.value

    def test_is_level_enabled_after_set(self) -> None:
        """Test is_level_enabled after set_level."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)

        assert logger.is_level_enabled(LogLevel.Trace) is True
        assert logger.is_level_enabled(LogLevel.Info) is True


class TestIsLevelEnabled:
    """Test is_level_enabled method."""

    def test_level_enabled_above_threshold(self) -> None:
        """Test that levels above threshold are enabled."""
        inner = PyLogger(LogLevel.Info)
        logger = Logger(inner)

        assert logger.is_level_enabled(LogLevel.Info) is True
        assert logger.is_level_enabled(LogLevel.Warning) is True
        assert logger.is_level_enabled(LogLevel.Error) is True

    def test_level_disabled_below_threshold(self) -> None:
        """Test that levels below threshold are disabled."""
        inner = PyLogger(LogLevel.Warning)
        logger = Logger(inner)
        logger.disable()

        assert logger.is_level_enabled(LogLevel.Debug) is False
        assert logger.is_level_enabled(LogLevel.Info) is False

    def test_level_enabled_with_string(self) -> None:
        """Test is_level_enabled with string levels."""
        inner = PyLogger(LogLevel.Info)
        logger = Logger(inner)

        assert logger.is_level_enabled("INFO") is True
        assert logger.is_level_enabled("ERROR") is True


class TestEnableDisable:
    """Test enable and disable methods for console output."""

    def test_disable_console(self) -> None:
        """Test disabling console output."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)

        assert logger.is_enabled() is True
        logger.disable()
        assert logger.is_enabled() is False

    def test_enable_console(self) -> None:
        """Test enabling console output."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        assert logger.is_enabled() is False
        logger.enable()
        assert logger.is_enabled() is True

    def test_enable_with_level(self) -> None:
        """Test enabling console with specific level."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        logger.enable(LogLevel.Warning)
        assert logger.is_enabled() is True

    def test_enable_with_string_level(self) -> None:
        """Test enabling console with string level."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        logger.enable("ERROR")
        assert logger.is_enabled() is True
