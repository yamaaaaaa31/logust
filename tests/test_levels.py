"""Tests for log levels and custom levels."""

from __future__ import annotations

from pathlib import Path

import pytest

from logust import Level, Logger, LogLevel
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

    def test_custom_emit_no_above_builtin_range_callable_needs_caller(self) -> None:
        """Severity ``no`` above 50: Python must still pre-collect for ``{function}`` sinks."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()

        logger.level("AUDIT", no=60, color="white")
        out: list[str] = []

        def sink(msg: str) -> None:
            out.append(msg)

        # Callable threshold uses built-in ``LogLevel``; emit via numeric custom ``no``.
        logger.add(sink, format="{function}", level=LogLevel.Trace)

        def emit_audit() -> None:
            logger.log(60, "msg")

        emit_audit()
        assert len(out) == 1
        assert "emit_audit" in out[0]


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

    def test_is_level_enabled_callback_only_matches_callback_threshold(self) -> None:
        """Callbacks alone determine cached_min_level; no file/console handlers needed."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()
        logger.add_callback(lambda _r: None, level="ERROR")

        assert logger.is_level_enabled(LogLevel.Debug) is False
        assert logger.is_level_enabled(LogLevel.Error) is True

    def test_is_level_enabled_after_remove_callback(self) -> None:
        """Removing a callback must refresh enablement (cached_min_level includes callbacks)."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.remove()
        cb_id = logger.add_callback(lambda _r: None, level="ERROR")

        assert logger.is_level_enabled(LogLevel.Debug) is False
        assert logger.is_level_enabled(LogLevel.Error) is True

        assert logger.remove_callback(cb_id) is True

        assert logger.is_level_enabled(LogLevel.Debug) is False
        assert logger.is_level_enabled(LogLevel.Error) is False


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


class TestLevelLookupAndUpdate:
    """Test ``logger.level(name)`` lookup and color/icon updates (loguru parity)."""

    def test_lookup_builtin_level(self) -> None:
        logger = Logger(PyLogger(LogLevel.Trace))

        info = logger.level("INFO")

        assert isinstance(info, Level)
        assert info == Level("INFO", 20, "green", "")
        assert (info.name, info.no) == ("INFO", 20)

    def test_lookup_is_case_insensitive(self) -> None:
        logger = Logger(PyLogger(LogLevel.Trace))

        assert logger.level("warning").no == 30

    def test_lookup_custom_level(self) -> None:
        logger = Logger(PyLogger(LogLevel.Trace))
        logger.level("LOOKUP_LVL", no=33, color="cyan", icon="@")

        assert logger.level("LOOKUP_LVL") == Level("LOOKUP_LVL", 33, "cyan", "@")

    def test_register_returns_level(self) -> None:
        logger = Logger(PyLogger(LogLevel.Trace))

        info = logger.level("RETURNED_LVL", no=34, color="red")

        assert info == Level("RETURNED_LVL", 34, "red", "")

    def test_register_positional_no(self) -> None:
        logger = Logger(PyLogger(LogLevel.Trace))

        assert logger.level("POSITIONAL_LVL", 36).no == 36

    def test_unknown_level_raises(self) -> None:
        logger = Logger(PyLogger(LogLevel.Trace))

        with pytest.raises(ValueError, match="does not exist"):
            logger.level("NO_SUCH_LEVEL")

    def test_update_unknown_level_raises(self) -> None:
        logger = Logger(PyLogger(LogLevel.Trace))

        with pytest.raises(ValueError, match="does not exist"):
            logger.level("NO_SUCH_LEVEL", color="red")

    def test_update_custom_level_keeps_no(self) -> None:
        logger = Logger(PyLogger(LogLevel.Trace))
        logger.level("UPDATE_LVL", no=37, color="cyan", icon="a")

        updated = logger.level("UPDATE_LVL", icon="b")

        assert updated == Level("UPDATE_LVL", 37, "cyan", "b")
        assert logger.level("UPDATE_LVL", color="blue") == Level("UPDATE_LVL", 37, "blue", "b")

    def test_update_builtin_color_applies_to_output(self, tmp_path: Path) -> None:
        logger = Logger(PyLogger(LogLevel.Trace))
        logger.disable()
        log_file = tmp_path / "color.log"
        file_id = logger.add(log_file, format="{level} {message}", colorize=True)
        messages: list[str] = []
        logger.add(messages.append, format="{level}", colorize=True)

        try:
            updated = logger.level("FAIL", color="bright_blue")
            assert updated == Level("FAIL", 45, "bright_blue", "")

            logger.fail("x")
            logger.complete()

            # Rust file sink and Python callable sink both use the new color
            assert "\x1b[1;94mFAIL" in log_file.read_text()
            assert messages == ["\x1b[1;94mFAIL\x1b[0m"]
        finally:
            logger.level("FAIL", color="magenta")
            logger.remove(file_id)

        assert logger.level("FAIL") == Level("FAIL", 45, "magenta", "")

    def test_configure_levels_updates_existing(self) -> None:
        logger = Logger(PyLogger(LogLevel.Trace))
        logger.level("CONFIGURED_LVL", no=38, color="cyan")

        logger.configure(levels=[{"name": "CONFIGURED_LVL", "icon": "*"}])

        assert logger.level("CONFIGURED_LVL") == Level("CONFIGURED_LVL", 38, "cyan", "*")

    def test_configure_levels_unknown_without_no_raises(self) -> None:
        logger = Logger(PyLogger(LogLevel.Trace))

        with pytest.raises(ValueError, match="does not exist"):
            logger.configure(levels=[{"name": "NO_SUCH_LEVEL", "color": "red"}])
