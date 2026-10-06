"""``add(filter=...)`` with a module name (str) or a level per module (dict),
and callable filters that raise.

String and dict filters follow loguru's rules and are checked in Rust; a
callable filter that raises drops the record, and the error follows the
handler's ``catch=`` policy.
"""

from __future__ import annotations

import builtins
import io
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from logust import CallerInfo, CollectOptions, Logger, LogLevel
from logust._logust import PyLogger

MODULES = ["app", "app.db", "app.db.pool", "appx", "lib", "lib.http", "__main__"]
LEVELS = ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR"]


@pytest.fixture
def logger() -> Logger:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.remove()
    return logger


def log_from(logger: Logger, module: str, level: str, message: str) -> None:
    """Log as if the call was made in module ``module`` (its ``__name__``)."""
    code = compile("logger.log(level, message)", f"<{module}>", "exec")
    exec(code, {"__name__": module, "logger": logger, "level": level, "message": message})


def emit_all(logger: Logger) -> None:
    for module in MODULES:
        for level in LEVELS:
            log_from(logger, module, level, f"{module} {level}")


def file_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


# What loguru keeps for each filter (checked against loguru in
# test_matches_loguru below).
STR_CASES: list[tuple[str, set[str]]] = [
    ("app", {"app", "app.db", "app.db.pool"}),
    ("app.db", {"app.db", "app.db.pool"}),
    ("lib", {"lib", "lib.http"}),
    ("", set(MODULES)),
    ("nothing", set()),
]


def expected_for_str(module_filter: str) -> list[str]:
    keep = dict(STR_CASES)[module_filter]
    return [f"{m} {lvl}" for m in MODULES for lvl in LEVELS if m in keep]


LEVEL_NO = {"TRACE": 5, "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}


def expected_for_dict(levels: dict[str | None, Any]) -> list[str]:
    """Reference implementation of loguru's ``filter_by_level``."""

    def min_no(value: Any) -> int | bool:
        if value is False or value is True:
            return 0 if value else False
        if isinstance(value, str):
            return LEVEL_NO[value]
        return int(value)

    resolved = {k: min_no(v) for k, v in levels.items()}
    out = []
    for module in MODULES:
        for level in LEVELS:
            name = module
            while True:
                found = resolved.get(name)
                if found is False:
                    keep = False
                    break
                if found is not None:
                    keep = LEVEL_NO[level] >= found
                    break
                if not name:
                    keep = True
                    break
                name = name.rpartition(".")[0]
            if keep:
                out.append(f"{module} {level}")
    return out


DICT_CASES: list[dict[str | None, Any]] = [
    {"": "WARNING", "app": "DEBUG", "app.db.pool": False},
    {"app": 30},
    {"": False, "lib": True},
    {"app.db": "ERROR", "app": "TRACE"},
    {"": "INFO"},
    {},
]


class TestStrFilter:
    @pytest.mark.parametrize("module_filter", [c[0] for c in STR_CASES])
    def test_file_sink(self, logger: Logger, tmp_path: Path, module_filter: str) -> None:
        path = tmp_path / "out.log"
        logger.add(path, level="TRACE", format="{message}", filter=module_filter)
        emit_all(logger)
        logger.complete()
        assert file_lines(path) == expected_for_str(module_filter)

    @pytest.mark.parametrize("module_filter", [c[0] for c in STR_CASES])
    def test_stream_sink(self, logger: Logger, module_filter: str) -> None:
        stream = io.StringIO()
        logger.add(stream, level="TRACE", format="{message}", filter=module_filter)
        emit_all(logger)
        assert stream.getvalue().splitlines() == expected_for_str(module_filter)

    def test_console_sink(self, logger: Logger, capfd: pytest.CaptureFixture[str]) -> None:
        logger.add(sys.__stdout__, level="TRACE", format="{message}", filter="app.db")
        emit_all(logger)
        assert capfd.readouterr().out.splitlines() == expected_for_str("app.db")

    def test_callable_sink_serialized(self, logger: Logger) -> None:
        lines: list[str] = []
        logger.add(lines.append, level="TRACE", serialize=True, filter="lib")
        emit_all(logger)
        assert len(lines) == len(expected_for_str("lib"))
        assert all('"name": "lib' in line for line in lines)

    def test_prefix_without_dot_does_not_match(self, logger: Logger) -> None:
        lines: list[str] = []
        logger.add(lines.append, format="{name}", filter="app")
        log_from(logger, "appx", "INFO", "x")
        log_from(logger, "app_extra", "INFO", "x")
        log_from(logger, "app.sub", "INFO", "x")
        assert lines == ["app.sub"]

    def test_works_when_caller_collection_is_off(self, logger: Logger, tmp_path: Path) -> None:
        """The filter needs the module name even if the format doesn't show it."""
        path = tmp_path / "out.log"
        logger.add(path, format="{message}", filter="app", collect=CollectOptions(caller=False))
        log_from(logger, "app", "INFO", "kept")
        log_from(logger, "lib", "INFO", "dropped")
        logger.complete()
        assert file_lines(path) == ["kept"]

    def test_fixed_caller_info_is_filtered(self, logger: Logger) -> None:
        lines: list[str] = []
        logger.add(
            lines.append,
            format="{message}",
            filter="app",
            collect=CollectOptions(caller=CallerInfo(name="lib", function="f", line=1)),
        )
        logger.info("dropped")
        assert lines == []

    def test_not_tracked_as_python_filter(self, logger: Logger, tmp_path: Path) -> None:
        """String / dict filters don't force full Python record dicts."""
        file_id = logger.add(tmp_path / "a.log", filter="app")
        stream_id = logger.add(io.StringIO(), filter={"": "INFO"})
        assert file_id not in logger._filter_ids
        assert stream_id not in logger._filter_ids


class TestDictFilter:
    @pytest.mark.parametrize("levels", DICT_CASES)
    def test_file_sink(self, logger: Logger, tmp_path: Path, levels: dict[str | None, Any]) -> None:
        path = tmp_path / "out.log"
        logger.add(path, level="TRACE", format="{message}", filter=levels)
        emit_all(logger)
        logger.complete()
        assert file_lines(path) == expected_for_dict(levels)

    @pytest.mark.parametrize("levels", DICT_CASES)
    def test_stream_sink(self, logger: Logger, levels: dict[str | None, Any]) -> None:
        stream = io.StringIO()
        logger.add(stream, level="TRACE", format="{message}", filter=levels)
        emit_all(logger)
        assert stream.getvalue().splitlines() == expected_for_dict(levels)

    def test_handler_level_still_applies(self, logger: Logger, tmp_path: Path) -> None:
        path = tmp_path / "out.log"
        logger.add(path, level="WARNING", format="{message}", filter={"app": "TRACE"})
        log_from(logger, "app", "INFO", "below handler level")
        log_from(logger, "app", "ERROR", "kept")
        logger.complete()
        assert file_lines(path) == ["kept"]

    def test_custom_level_name(self, logger: Logger, tmp_path: Path) -> None:
        logger.level("NOTICE", no=35)
        path = tmp_path / "out.log"
        logger.add(path, level="TRACE", format="{message}", filter={"app": "NOTICE"})
        log_from(logger, "app", "WARNING", "dropped")
        log_from(logger, "app", "NOTICE", "notice")
        log_from(logger, "app", "ERROR", "error")
        logger.complete()
        assert file_lines(path) == ["notice", "error"]

    def test_level_is_resolved_at_add_time(self, logger: Logger) -> None:
        with pytest.raises(ValueError, match="level name which does not exist: 'LATER'"):
            logger.add(io.StringIO(), filter={"app": "LATER"})

    def test_huge_level_number_drops_everything(self, logger: Logger) -> None:
        lines: list[str] = []
        logger.add(lines.append, format="{message}", filter={"app": 2**70})
        log_from(logger, "app", "CRITICAL", "dropped")
        log_from(logger, "lib", "INFO", "kept")
        assert lines == ["kept"]


SINKS: dict[str, Callable[[Path], Any]] = {
    "file": lambda tmp: tmp / "out.log",
    "stream": lambda _tmp: io.StringIO(),
    "callable": lambda _tmp: lambda _m: None,
    "console": lambda _tmp: sys.__stderr__,
}


class TestValidation:
    @pytest.mark.parametrize("sink", SINKS)
    @pytest.mark.parametrize(
        ("bad", "error", "match"),
        [
            (
                1,
                TypeError,
                "Invalid filter, it should be a function, a string or a dict, not: 'int'",
            ),
            (["app"], TypeError, "not: 'list'"),
            ({1: "INFO"}, TypeError, "invalid module, it should be a string \\(or None\\)"),
            ({"app": "NOPE"}, ValueError, "level name which does not exist: 'NOPE'"),
            ({"app": -1}, ValueError, "should be a positive integer, not: '-1'"),
            ({"app": 1.5}, TypeError, "integer, a string or a boolean, not: 'float'"),
            ({"app": None}, TypeError, "not: 'NoneType'"),
            (builtins.filter, ValueError, "built-in 'filter\\(\\)' function"),
        ],
    )
    def test_rejected_at_add(
        self,
        logger: Logger,
        tmp_path: Path,
        sink: str,
        bad: Any,
        error: type[Exception],
        match: str,
    ) -> None:
        with pytest.raises(error, match=match):
            logger.add(SINKS[sink](tmp_path), filter=bad)
        # Nothing was registered
        assert logger._inner.handler_count == 0
        assert not logger._callback_ids
        if sink == "file":
            assert not (tmp_path / "out.log").exists()

    def test_none_key_is_accepted(self, logger: Logger) -> None:
        lines: list[str] = []
        logger.add(lines.append, format="{message}", filter={None: False, "": "INFO"})
        log_from(logger, "app", "INFO", "kept")
        assert lines == ["kept"]


def raising_filter(_record: dict[str, Any]) -> bool:
    raise ZeroDivisionError("filter bug")


class TestRaisingFilter:
    """A filter that raises drops the record; the error follows ``catch=``."""

    @pytest.mark.parametrize("sink", ["file", "stream", "console"])
    def test_default_drops_record_silently(
        self,
        logger: Logger,
        tmp_path: Path,
        capfd: pytest.CaptureFixture[str],
        sink: str,
    ) -> None:
        good = io.StringIO()
        target = SINKS[sink](tmp_path)
        logger.add(target, format="{message}", filter=raising_filter)
        logger.add(good, format="{message}")
        logger.info("hello")
        logger.complete()
        assert good.getvalue() == "hello\n"
        if sink == "file":
            assert file_lines(target) == []
        elif sink == "stream":
            assert target.getvalue() == ""
        assert capfd.readouterr().err == ""

    @pytest.mark.parametrize("sink", ["file", "stream", "console"])
    def test_catch_true_reports_and_drops(
        self,
        logger: Logger,
        tmp_path: Path,
        capfd: pytest.CaptureFixture[str],
        sink: str,
    ) -> None:
        good = io.StringIO()
        target = SINKS[sink](tmp_path)
        handler_id = logger.add(target, format="{message}", filter=raising_filter, catch=True)
        logger.add(good, format="{message}")
        logger.info("hello")
        logger.complete()
        assert good.getvalue() == "hello\n"
        err = capfd.readouterr().err
        assert f"--- Logging error in Logust Handler #{handler_id} ---" in err
        assert "Record was: " in err and "hello" in err
        assert "ZeroDivisionError: filter bug" in err
        assert "in raising_filter" in err
        assert err.rstrip().endswith("--- End of logging error ---")
        if sink == "file":
            assert file_lines(target) == []
        elif sink == "stream":
            assert target.getvalue() == ""

    @pytest.mark.parametrize("sink", ["file", "stream", "console"])
    def test_catch_false_raises_after_other_handlers(
        self, logger: Logger, tmp_path: Path, sink: str
    ) -> None:
        good = io.StringIO()
        logger.add(SINKS[sink](tmp_path), format="{message}", filter=raising_filter, catch=False)
        logger.add(good, format="{message}")
        with pytest.raises(ZeroDivisionError, match="filter bug"):
            logger.info("hello")
        assert good.getvalue() == "hello\n"

    def test_custom_level_path(self, logger: Logger, capfd: pytest.CaptureFixture[str]) -> None:
        logger.level("NOTICE", no=25)
        logger.add(sys.__stdout__, format="{message}", filter=raising_filter, catch=True)
        logger.log("NOTICE", "custom")
        captured = capfd.readouterr()
        assert captured.out == ""
        assert "ZeroDivisionError: filter bug" in captured.err

    def test_falsy_truthiness_error_is_a_filter_error(self, logger: Logger) -> None:
        class Bad:
            def __bool__(self) -> bool:
                raise RuntimeError("no truth value")

        logger.add(io.StringIO(), filter=lambda _r: Bad(), catch=False)
        with pytest.raises(RuntimeError, match="no truth value"):
            logger.info("x")


class TestMatchesLoguru:
    """Same records kept as loguru for the same filter."""

    @pytest.mark.parametrize("flt", [c[0] for c in STR_CASES] + DICT_CASES, ids=repr)
    def test_matches_loguru(self, logger: Logger, flt: Any) -> None:
        loguru = pytest.importorskip("loguru")
        theirs: list[str] = []
        loguru.logger.remove()
        loguru.logger.add(lambda m: theirs.append(m.record["message"]), level=0, filter=flt)
        try:
            for module in MODULES:
                for level in LEVELS:
                    loguru.logger.patch(
                        lambda r, n=module: r.update(name=n)  # type: ignore[call-arg,misc]
                    ).log(level, f"{module} {level}")
        finally:
            loguru.logger.remove()

        ours: list[str] = []
        logger.add(ours.append, level="TRACE", format="{message}", filter=flt)
        emit_all(logger)
        assert ours == theirs
