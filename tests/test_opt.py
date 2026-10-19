"""Tests for OptLogger (logger.opt())."""

from __future__ import annotations

from pathlib import Path

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger


@pytest.mark.parametrize(
    ("method", "no"),
    [
        ("trace", 5),
        ("debug", 10),
        ("info", 20),
        ("success", 25),
        ("warning", 30),
        ("error", 40),
        ("fail", 45),
        ("critical", 50),
    ],
)
def test_opt_threshold_refresh_precedes_option_side_effects(
    method: str, no: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.remove()
    out: list[str] = []
    logger.add(out.append, format="{message}", level=no + 1)
    opt = logger.opt(lazy=True, exception=True, capture=False)
    effects: list[str] = []

    def lazy_value() -> str:
        effects.append("lazy")
        return "arg"

    class Formatted:
        def __format__(self, _spec: str) -> str:
            effects.append("format")
            return "value"

    def capture(*_args: object, **_kwargs: object) -> str:
        effects.append("exception")
        return "trace text"

    monkeypatch.setattr("logust._opt.capture_exception", capture)
    try:
        raise ValueError("already active")
    except ValueError:
        emit = getattr(opt, method)
        emit("{} {value}", lazy_value, value=Formatted())
        assert effects == []
        assert out == []

        # Reuse the same OptLogger across handler threshold changes.
        low = logger.add(out.append, format="{message}", level=no)
        emit("{} {value}", lazy_value, value=Formatted())
        assert effects == ["lazy", "exception", "format"]
        assert out == ["arg value\ntrace text"]

        assert logger.remove(low)
        effects.clear()
        emit("{} {value}", lazy_value, value=Formatted())
        assert effects == []
        assert out == ["arg value\ntrace text"]
    finally:
        logger.remove()


def test_opt_threshold_tracks_callback_console_and_module_changes(
    capfd: pytest.CaptureFixture[str],
) -> None:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.remove()
    opt = logger.opt(lazy=True)
    calls: list[int] = []
    records: list[dict] = []

    def value() -> str:
        calls.append(1)
        return "opt-enabled"

    opt.error("{}", value)
    assert calls == []
    callback = logger.add_callback(records.append, level="ERROR")
    opt.error("{}", value)
    assert len(calls) == 1
    assert [record["message"] for record in records] == ["opt-enabled"]
    assert logger.remove_callback(callback)
    opt.error("{}", value)
    assert len(calls) == 1

    logger.enable(level="ERROR")
    opt.error("{}", value)
    assert len(calls) == 2
    logger.set_level("CRITICAL")
    opt.error("{}", value)
    assert len(calls) == 2
    logger.set_level("ERROR")
    logger.disable(__name__)
    opt.error("{}", value)
    assert len(calls) == 2
    logger.enable(__name__)
    opt.error("{}", value)
    assert len(calls) == 3
    logger.disable()
    opt.error("{}", value)
    assert len(calls) == 3
    logger.remove()
    assert capfd.readouterr().err.count("opt-enabled") == 2


class TestLazyEvaluation:
    """Test lazy argument evaluation."""

    def test_lazy_callable_evaluated(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test that callable arguments are evaluated when lazy=True."""
        logger, log_file = logger_with_file

        call_count = 0

        def expensive_func() -> str:
            nonlocal call_count
            call_count += 1
            return "computed"

        logger.opt(lazy=True).info("Result: {}", expensive_func)
        logger.complete()

        assert call_count == 1
        content = log_file.read_text()
        assert "Result: computed" in content

    def test_lazy_skips_when_level_disabled(self) -> None:
        """Test that callable is NOT called when level is disabled."""
        inner = PyLogger(LogLevel.Warning)
        logger = Logger(inner)
        logger.disable()

        call_count = 0

        def expensive_func() -> str:
            nonlocal call_count
            call_count += 1
            return "computed"

        logger.opt(lazy=True).debug("Result: {}", expensive_func)
        logger.complete()

        assert call_count == 0


class TestException:
    """Test exception auto-capture."""

    def test_opt_exception_captures_traceback(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test that opt(exception=True) captures traceback."""
        logger, log_file = logger_with_file

        try:
            raise ValueError("Test exception")
        except ValueError:
            logger.opt(exception=True).error("Caught error")

        logger.complete()

        content = log_file.read_text()
        assert "ValueError" in content
        assert "Test exception" in content

    def test_opt_exception_outside_handler(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test opt(exception=True) outside except block."""
        logger, log_file = logger_with_file

        logger.opt(exception=True).info("No exception here")
        logger.complete()

        content = log_file.read_text()
        assert "No exception here" in content


class TestBacktrace:
    """Test backtrace extension."""

    def test_backtrace_extended(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test that backtrace=True shows extended trace."""
        logger, log_file = logger_with_file

        def inner_func() -> None:
            raise RuntimeError("Deep error")

        def outer_func() -> None:
            inner_func()

        try:
            outer_func()
        except RuntimeError:
            logger.opt(backtrace=True).error("Extended trace")

        logger.complete()

        content = log_file.read_text()
        assert "RuntimeError" in content
        assert "Deep error" in content


class TestDiagnose:
    """Test variable diagnosis."""

    def test_diagnose_shows_variables(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test that diagnose=True shows variable values."""
        logger, log_file = logger_with_file

        try:
            a = 10
            b = 0
            _ = a / b
        except ZeroDivisionError:
            logger.opt(diagnose=True).error("Division failed")

        logger.complete()

        content = log_file.read_text()
        assert "ZeroDivisionError" in content


class TestOptChaining:
    """Test chaining opt() with other methods."""

    def test_opt_with_bind(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test using opt() with bound logger."""
        logger, log_file = logger_with_file

        bound = logger.bind(user="alice")
        bound.opt(lazy=True).info("Bound lazy: {}", lambda: "computed")
        logger.complete()

        content = log_file.read_text()
        assert "Bound lazy: computed" in content


class TestOptAllLevels:
    """Test opt() works with all log levels."""

    def test_all_levels(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test opt() with each log level."""
        logger, log_file = logger_with_file

        opt = logger.opt(lazy=True)
        opt.trace("Trace: {}", lambda: "t")
        opt.debug("Debug: {}", lambda: "d")
        opt.info("Info: {}", lambda: "i")
        opt.success("Success: {}", lambda: "s")
        opt.warning("Warning: {}", lambda: "w")
        opt.error("Error: {}", lambda: "e")
        opt.fail("Fail: {}", lambda: "f")
        opt.critical("Critical: {}", lambda: "c")

        logger.complete()

        content = log_file.read_text()
        assert "Trace: t" in content
        assert "Debug: d" in content
        assert "Info: i" in content
        assert "Success: s" in content
        assert "Warning: w" in content
        assert "Error: e" in content
        assert "Fail: f" in content
        assert "Critical: c" in content

    def test_opt_log_method(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test opt().log() with custom level."""
        logger, log_file = logger_with_file

        logger.level("CUSTOM", no=22)
        logger.opt(lazy=True).log("CUSTOM", "Custom: {}", lambda: "value")
        logger.complete()

        content = log_file.read_text()
        assert "Custom: value" in content
