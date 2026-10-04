"""Tests for loguru format fields: {time:<spec>}, {level.*}, {exception}, dotted attributes."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from logust import Logger, LogLevel
from logust._logger import _collect_options_from_format
from logust._logust import PyLogger, TimeFormatter
from logust._template import ParsedCallableTemplate

HERE = os.path.abspath(__file__)


def _logger() -> Logger:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.remove()
    return logger


def _render_file(tmp_path: Path, fmt: str, emit: str = "info", message: str = "msg") -> str:
    logger = _logger()
    log_file = tmp_path / "out.log"
    logger.add(str(log_file), format=fmt, level="TRACE")
    getattr(logger, emit)(message)
    logger.complete()
    return log_file.read_text().rstrip("\n")


def _render_callable(fmt: str, emit: str = "info", message: str = "msg", **add: object) -> str:
    logger = _logger()
    out: list[str] = []
    logger.add(out.append, format=fmt, level="TRACE", **add)  # type: ignore[arg-type]
    getattr(logger, emit)(message)
    assert len(out) == 1
    return out[0]


class TestTimeSpec:
    def test_date_only(self, tmp_path: Path) -> None:
        line = _render_file(tmp_path, "{time:YYYY-MM-DD} {message}")
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} msg", line), line
        assert line[:10] == datetime.now().strftime("%Y-%m-%d")

    def test_tokens_and_escape(self, tmp_path: Path) -> None:
        line = _render_file(tmp_path, "{time:[YYYY] HH:mm:ss.SSSSSS A ZZ}")
        assert re.fullmatch(r"YYYY \d{2}:\d{2}:\d{2}\.\d{6} (AM|PM) [+-]\d{4}", line), line

    def test_utc(self, tmp_path: Path) -> None:
        line = _render_file(tmp_path, "{time:HH Z!UTC}")
        assert line == datetime.now(timezone.utc).strftime("%H") + " +00:00"

    def test_strftime_spec(self, tmp_path: Path) -> None:
        line = _render_file(tmp_path, "{time:%Y/%m/%d %f}")
        assert re.fullmatch(r"\d{4}/\d{2}/\d{2} \d{6}", line), line

    def test_empty_spec_is_iso(self, tmp_path: Path) -> None:
        line = _render_file(tmp_path, "{time:}")
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}[+-]\d{4}", line), line

    def test_plain_time_unchanged(self, tmp_path: Path) -> None:
        line = _render_file(tmp_path, "{time}")
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}", line), line

    def test_invalid_spec_raises(self, tmp_path: Path) -> None:
        logger = _logger()
        with pytest.raises(ValueError, match="six"):
            logger.add(str(tmp_path / "x.log"), format="{time:SSSSSSS}")
        with pytest.raises(ValueError):
            logger.add(lambda _m: None, format="{time:SSSSSSS}")
        assert logger._inner.handler_count == 0

    def test_callable_matches_file(self, tmp_path: Path) -> None:
        fmt = "{time:YYYY-MM-DD dddd MMMM Q}"
        assert _render_callable(fmt) == _render_file(tmp_path, fmt)

    def test_time_formatter(self) -> None:
        fmt = TimeFormatter("YYYY-MM-DD HH:mm:ss.SSS Z")
        assert (
            fmt.format_rfc3339("2024-03-05T14:07:09.123456+09:00")
            == "2024-03-05 14:07:09.123 +09:00"
        )
        assert fmt.format_rfc3339("") == ""


class TestLevelFields:
    def test_builtin(self, tmp_path: Path) -> None:
        line = _render_file(tmp_path, "{level.name}|{level.no}|{level.icon}", emit="warning")
        assert line == "WARNING|30|⚠️"

    def test_level_name_width(self, tmp_path: Path) -> None:
        assert _render_file(tmp_path, "{level.name:<8}|") == "INFO    |"

    def test_custom_level_icon(self, tmp_path: Path) -> None:
        logger = _logger()
        logger.level("NOTICE_ICON", no=33, icon="@")
        log_file = tmp_path / "custom.log"
        out: list[str] = []
        fmt = "{level.name}|{level.no}|{level.icon}|{message}"
        logger.add(str(log_file), format=fmt)
        logger.add(out.append, format=fmt)
        logger.log("NOTICE_ICON", "m")
        logger.complete()
        assert log_file.read_text().strip() == "NOTICE_ICON|33|@|m"
        assert out == ["NOTICE_ICON|33|@|m"]

    def test_callable_matches_file(self, tmp_path: Path) -> None:
        fmt = "{level.name}|{level.no}|{level.icon}"
        assert _render_callable(fmt, emit="success") == _render_file(tmp_path, fmt, emit="success")


class TestExceptionField:
    def _emit(self, logger: Logger) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("failed")

    def test_placed_once(self, tmp_path: Path) -> None:
        logger = _logger()
        log_file = tmp_path / "exc.log"
        out: list[str] = []
        fmt = "{message} [{exception}] end"
        logger.add(str(log_file), format=fmt)
        logger.add(out.append, format=fmt)
        self._emit(logger)
        logger.complete()
        text = log_file.read_text()
        assert text.count("ValueError: boom") == 1
        assert text.startswith("failed [Traceback")
        assert text.rstrip("\n").endswith("] end")
        assert out[0] == text.rstrip("\n")

    def test_empty_without_exception(self, tmp_path: Path) -> None:
        assert _render_file(tmp_path, "{message}[{exception}]") == "msg[]"
        assert _render_callable("{message}[{exception}]") == "msg[]"

    def test_auto_appended_without_token(self, tmp_path: Path) -> None:
        logger = _logger()
        log_file = tmp_path / "exc.log"
        logger.add(str(log_file), format="{message}")
        self._emit(logger)
        logger.complete()
        assert log_file.read_text().startswith("failed\nTraceback")


class TestDottedFields:
    def test_thread_process(self, tmp_path: Path) -> None:
        fmt = "{thread.name}|{thread.id}|{process.name}|{process.id}"
        expected = (
            f"{threading.current_thread().name}|{threading.get_ident()}|MainProcess|{os.getpid()}"
        )
        assert _render_file(tmp_path, fmt) == expected
        assert _render_callable(fmt) == expected

    def test_file_name_and_path(self, tmp_path: Path) -> None:
        fmt = "{file}|{file.name}|{file.path}"
        expected = f"{os.path.basename(HERE)}|{os.path.basename(HERE)}|{HERE}"
        assert _render_file(tmp_path, fmt) == expected
        assert _render_callable(fmt) == expected
        # Filtered callable sinks receive the full record dict
        assert _render_callable(fmt, filter=lambda _r: True) == expected

    def test_record_dicts_keep_file_basename(self) -> None:
        logger = _logger()
        records: list[dict[str, object]] = []
        logger.add_callback(records.append)
        logger.info("m")
        assert records[0]["file"] == os.path.basename(HERE)
        assert "file_path" not in records[0]

    def test_unknown_attribute_literal(self, tmp_path: Path) -> None:
        assert _render_file(tmp_path, "{level.color}|{message}") == "{level.color}|msg"
        assert _render_callable("{level.color}|{message}") == "{level.color}|msg"


class TestCollectDetection:
    @pytest.mark.parametrize(
        ("fmt", "expected"),
        [
            ("{thread.name}", (False, True, False)),
            ("{thread.id}", (False, True, False)),
            ("{process.id}", (False, False, True)),
            ("{file.path}", (True, False, False)),
            ("{file.name}", (True, False, False)),
            ("{level.icon} {time:HH} {exception}", (False, False, False)),
        ],
    )
    def test_collect_options_from_format(self, fmt: str, expected: tuple[bool, bool, bool]) -> None:
        opts = _collect_options_from_format(fmt)
        assert (opts.caller, opts.thread, opts.process) == expected

    @pytest.mark.parametrize(
        ("fmt", "expected"),
        [
            ("{thread.id}", (False, True, False)),
            ("{process.name}", (False, False, True)),
            ("{file.path}", (True, False, False)),
            ("{level.no} {time:YYYY}", (False, False, False)),
        ],
    )
    def test_rust_requirements(
        self, tmp_path: Path, fmt: str, expected: tuple[bool, bool, bool]
    ) -> None:
        logger = _logger()
        logger.add(str(tmp_path / "x.log"), format=fmt)
        inner = logger._inner
        assert (
            inner.needs_caller_info,
            inner.needs_thread_info,
            inner.needs_process_info,
        ) == expected


class TestSerializeUnchanged:
    def test_json_keys(self, tmp_path: Path) -> None:
        logger = _logger()
        log_file = tmp_path / "x.json"
        logger.add(str(log_file), format="{time:YYYY} {level.icon} {file.path}", serialize=True)
        logger.info("m")
        logger.complete()
        record = json.loads(log_file.read_text())
        assert set(record) == {"time", "level", "message", "name", "function", "line"}
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}", record["time"])


class TestCallableTemplateSegments:
    def test_time_spec_compiled(self) -> None:
        template = ParsedCallableTemplate("{time:YYYY}")
        record = {"timestamp": "2024-03-05T14:07:09.123456+09:00"}
        assert template.format(record) == "2024"

    def test_colorized_styles(self) -> None:
        template = ParsedCallableTemplate("{level.name} {thread.id}", colorize=True)
        out = template.format({"level": "INFO", "thread_id": 1})
        assert out == "\x1b[1;32mINFO\x1b[0m \x1b[36m1\x1b[0m"
