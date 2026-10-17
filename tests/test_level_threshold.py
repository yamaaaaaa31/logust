"""Level thresholds: built-in names, custom level names, ints and ``LogLevel``.

A record passes a ``level=`` threshold when its ``no`` is at least the
threshold's value (loguru's semantics), custom levels included.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from logust import Logger, LogLevel

# Registered once per test process; the level registry is global.
# NOTICE=25 matches tests/test_levels.py, MID=23 sits between INFO and SUCCESS.
NOTICE_NO = 25
MID_NO = 23

# Threshold spellings that all mean "23 and above"
MID_THRESHOLDS: list[Any] = ["T_MID", "t_mid", MID_NO]


@pytest.fixture(autouse=True)
def _custom_levels(fresh_logger: Logger) -> None:
    fresh_logger.level("NOTICE", no=NOTICE_NO, color="cyan")
    fresh_logger.level("T_MID", no=MID_NO, color="blue")


def _emit_all(logger: Logger) -> None:
    logger.debug("debug")
    logger.info("info")
    logger.log("T_MID", "mid")
    logger.success("success")
    logger.warning("warning")


ABOVE_MID = ["mid", "success", "warning"]


def _list_sink(logger: Logger, level: Any, **options: Any) -> list[str]:
    out: list[str] = []
    logger.add(out.append, level=level, format="{message}", **options)
    return out


def _messages(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip()]


class TestHandlerThresholds:
    @pytest.mark.parametrize("level", MID_THRESHOLDS)
    def test_callable_sink(self, fresh_logger: Logger, level: Any) -> None:
        out = _list_sink(fresh_logger, level)
        _emit_all(fresh_logger)
        assert _messages(out) == ABOVE_MID

    @pytest.mark.parametrize("level", MID_THRESHOLDS)
    def test_serialized_callable_sink(self, fresh_logger: Logger, level: Any) -> None:
        out: list[str] = []
        fresh_logger.add(out.append, level=level, serialize=True)
        _emit_all(fresh_logger)
        assert [json.loads(line)["message"] for line in out] == ABOVE_MID

    @pytest.mark.parametrize("level", MID_THRESHOLDS)
    def test_file_sink(self, fresh_logger: Logger, tmp_path: Path, level: Any) -> None:
        path = tmp_path / "app.log"
        fresh_logger.add(path, level=level, format="{message}")
        _emit_all(fresh_logger)
        fresh_logger.complete()
        assert _messages(path.read_text(encoding="utf-8").splitlines()) == ABOVE_MID

    @pytest.mark.parametrize("level", MID_THRESHOLDS)
    def test_serialized_file_sink(self, fresh_logger: Logger, tmp_path: Path, level: Any) -> None:
        path = tmp_path / "app.jsonl"
        fresh_logger.add(path, level=level, serialize=True)
        _emit_all(fresh_logger)
        fresh_logger.complete()
        lines = path.read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["message"] for line in lines] == ABOVE_MID

    @pytest.mark.parametrize("level", MID_THRESHOLDS)
    def test_console_sink(
        self, fresh_logger: Logger, capfd: pytest.CaptureFixture[str], level: Any
    ) -> None:
        fresh_logger.add(sys.__stderr__, level=level, format="{message}", colorize=False)  # type: ignore[arg-type]
        _emit_all(fresh_logger)
        assert _messages(capfd.readouterr().err.splitlines()) == ABOVE_MID

    @pytest.mark.parametrize("level", MID_THRESHOLDS)
    def test_add_callback(self, fresh_logger: Logger, level: Any) -> None:
        records: list[dict[str, Any]] = []
        fresh_logger.add_callback(records.append, level=level)
        _emit_all(fresh_logger)
        assert [r["message"] for r in records] == ABOVE_MID

    def test_log_level_enum_threshold(self, fresh_logger: Logger) -> None:
        out = _list_sink(fresh_logger, LogLevel.Success)
        _emit_all(fresh_logger)
        assert _messages(out) == ["success", "warning"]

    def test_builtin_name_is_case_insensitive(self, fresh_logger: Logger) -> None:
        out = _list_sink(fresh_logger, "Warning")
        _emit_all(fresh_logger)
        assert _messages(out) == ["warning"]

    def test_int_zero_passes_everything(self, fresh_logger: Logger) -> None:
        out = _list_sink(fresh_logger, 0)
        fresh_logger.trace("trace")
        fresh_logger.log("T_MID", "mid")
        assert _messages(out) == ["trace", "mid"]

    def test_custom_level_at_builtin_value(self, fresh_logger: Logger) -> None:
        """NOTICE=25: drops INFO=20, passes SUCCESS=25 and WARNING=30."""
        out = _list_sink(fresh_logger, "NOTICE")
        fresh_logger.info("info")
        fresh_logger.log("NOTICE", "notice")
        fresh_logger.success("success")
        fresh_logger.warning("warning")
        assert _messages(out) == ["notice", "success", "warning"]

    def test_huge_int_drops_everything(self, fresh_logger: Logger) -> None:
        out = _list_sink(fresh_logger, 2**40)
        fresh_logger.critical("critical")
        assert out == []

    def test_configure_handler_level(self, fresh_logger: Logger) -> None:
        out: list[str] = []
        fresh_logger.configure(
            handlers=[{"sink": out.append, "level": "T_MID", "format": "{message}"}]
        )
        _emit_all(fresh_logger)
        assert _messages(out) == ABOVE_MID

    def test_configure_registers_levels_before_handlers(self, fresh_logger: Logger) -> None:
        out: list[str] = []
        fresh_logger.configure(
            levels=[{"name": "T_CONF", "no": 33}],
            handlers=[{"sink": out.append, "level": "T_CONF", "format": "{message}"}],
        )
        fresh_logger.warning("warning")
        fresh_logger.log("T_CONF", "conf")
        fresh_logger.error("error")
        assert _messages(out) == ["conf", "error"]


class TestConsoleLevel:
    @pytest.mark.parametrize("level", MID_THRESHOLDS)
    def test_set_level(
        self, fresh_logger: Logger, capfd: pytest.CaptureFixture[str], level: Any
    ) -> None:
        fresh_logger.add(sys.__stderr__, format="{message}", colorize=False)  # type: ignore[arg-type]
        fresh_logger.set_level(level)
        _emit_all(fresh_logger)
        assert _messages(capfd.readouterr().err.splitlines()) == ABOVE_MID
        assert fresh_logger.get_level() == MID_NO

    def test_set_level_log_level(self, fresh_logger: Logger) -> None:
        fresh_logger.set_level(LogLevel.Warning)
        fresh_logger.enable()
        assert fresh_logger.get_level() == LogLevel.Warning

    def test_get_level_of_builtin_value_is_log_level(self, fresh_logger: Logger) -> None:
        fresh_logger.enable()
        fresh_logger.set_level(30)
        level = fresh_logger.get_level()
        assert isinstance(level, LogLevel)
        assert level == LogLevel.Warning
        fresh_logger.set_level(MID_NO)
        assert type(fresh_logger.get_level()) is int

    @pytest.mark.parametrize("level", MID_THRESHOLDS)
    def test_enable_level(
        self, fresh_logger: Logger, capfd: pytest.CaptureFixture[str], level: Any
    ) -> None:
        fresh_logger.enable(level=level)
        assert fresh_logger.get_level() == MID_NO
        assert not fresh_logger.is_level_enabled("INFO")
        assert fresh_logger.is_level_enabled("T_MID")
        capfd.readouterr()

    def test_enable_positional_int(self, fresh_logger: Logger) -> None:
        fresh_logger.enable(MID_NO)
        assert fresh_logger.get_level() == MID_NO

    def test_enable_log_level(self, fresh_logger: Logger) -> None:
        fresh_logger.enable(level=LogLevel.Error)
        assert fresh_logger.get_level() == LogLevel.Error


class TestIsLevelEnabled:
    def test_custom_name_int_and_log_level(self, fresh_logger: Logger) -> None:
        _list_sink(fresh_logger, "T_MID")
        assert fresh_logger.is_level_enabled("T_MID")
        assert fresh_logger.is_level_enabled("t_mid")
        assert fresh_logger.is_level_enabled("NOTICE")
        assert fresh_logger.is_level_enabled(MID_NO)
        assert not fresh_logger.is_level_enabled(MID_NO - 1)
        assert not fresh_logger.is_level_enabled("INFO")
        assert fresh_logger.is_level_enabled(LogLevel.Success)
        assert not fresh_logger.is_level_enabled(LogLevel.Info)


ENTRY_POINTS: dict[str, Callable[[Logger, Any], object]] = {
    "set_level": lambda lg, level: lg.set_level(level),
    "is_level_enabled": lambda lg, level: lg.is_level_enabled(level),
    "enable": lambda lg, level: lg.enable(level=level),
    "add_callable": lambda lg, level: lg.add(lambda _m: None, level=level),
    "add_serialized": lambda lg, level: lg.add(lambda _m: None, level=level, serialize=True),
    "add_console": lambda lg, level: lg.add(sys.__stderr__, level=level),  # type: ignore[arg-type]
    "add_callback": lambda lg, level: lg.add_callback(lambda _r: None, level=level),
    "configure": lambda lg, level: lg.configure(
        handlers=[{"sink": lambda _m: None, "level": level}]
    ),
}


class TestErrors:
    @pytest.mark.parametrize("entry", list(ENTRY_POINTS))
    def test_unknown_name(self, fresh_logger: Logger, entry: str) -> None:
        with pytest.raises(ValueError, match="Level 'NOPE' does not exist"):
            ENTRY_POINTS[entry](fresh_logger, "NOPE")

    @pytest.mark.parametrize("entry", list(ENTRY_POINTS))
    def test_negative_int(self, fresh_logger: Logger, entry: str) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            ENTRY_POINTS[entry](fresh_logger, -1)

    @pytest.mark.parametrize("entry", list(ENTRY_POINTS))
    @pytest.mark.parametrize("bad", [2.5, True, b"INFO", object()])
    def test_wrong_type(self, fresh_logger: Logger, entry: str, bad: object) -> None:
        with pytest.raises(TypeError, match="Invalid level"):
            ENTRY_POINTS[entry](fresh_logger, bad)

    def test_file_sink_unknown_name_creates_nothing(
        self, fresh_logger: Logger, tmp_path: Path
    ) -> None:
        path = tmp_path / "app.log"
        with pytest.raises(ValueError, match="does not exist"):
            fresh_logger.add(path, level="NOPE")
        assert not path.exists()

    def test_failed_add_leaves_no_handler(self, fresh_logger: Logger) -> None:
        count = fresh_logger._inner.handler_count
        for bad in ("NOPE", -1, 2.5):
            with pytest.raises((ValueError, TypeError)):
                fresh_logger.add(lambda _m: None, level=bad)
            with pytest.raises((ValueError, TypeError)):
                fresh_logger.add(sys.__stderr__, level=bad)  # type: ignore[arg-type]
        assert fresh_logger._inner.handler_count == count
        assert fresh_logger.is_level_enabled(LogLevel.Critical) is False


class TestLogWithLogLevel:
    def test_log_accepts_log_level(self, fresh_logger: Logger) -> None:
        out: list[str] = []
        fresh_logger.add(out.append, format="{level}|{message}", level="TRACE")
        fresh_logger.log(LogLevel.Warning, "warn {}", 1)
        fresh_logger.opt(lazy=True).log(LogLevel.Error, "err {}", lambda: 2)
        assert _messages(out) == ["WARNING|warn 1", "ERROR|err 2"]

    def test_log_level_below_threshold_is_dropped(self, fresh_logger: Logger) -> None:
        out = _list_sink(fresh_logger, "WARNING")
        fresh_logger.log(LogLevel.Info, "info")
        assert out == []


class TestLogLevelOrdering:
    def test_comparisons(self) -> None:
        assert LogLevel.Info < LogLevel.Error
        assert LogLevel.Error > LogLevel.Info
        assert LogLevel.Info <= LogLevel.Info
        assert LogLevel.Critical >= LogLevel.Fail
        assert not LogLevel.Warning < LogLevel.Success

    def test_sorted(self) -> None:
        levels = [LogLevel.Error, LogLevel.Trace, LogLevel.Warning, LogLevel.Debug]
        assert sorted(levels) == [LogLevel.Trace, LogLevel.Debug, LogLevel.Warning, LogLevel.Error]


def test_custom_levels_example_runs(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parent.parent / "examples" / "06_custom_levels.py"
    result = subprocess.run(
        [sys.executable, str(example)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "This will show (27 >= 27)" in result.stderr
    assert "This won't show" not in result.stderr
    assert "This will show (22 >= 18)" in result.stderr
