"""Tests for OptLogger (logger.opt())."""

from __future__ import annotations

from pathlib import Path

from logust import Logger, LogLevel
from logust._logust import PyLogger


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
