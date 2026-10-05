"""loguru-shaped record dicts for filters, patchers and raw callbacks."""

from __future__ import annotations

import datetime
import json
import os
import pickle
import re
import threading
from pathlib import Path
from typing import Any

import pytest

from logust import (
    Logger,
    LogLevel,
    RecordElapsed,
    RecordFile,
    RecordLevelStr,
    RecordProcess,
    RecordThread,
)
from logust._logust import PyLogger

_ELAPSED_RE = re.compile(r"^\d{2,}:\d{2}:\d{2}\.\d{3}$")


def _new_logger() -> Logger:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.disable()
    return logger


def _capture_filter(logger: Logger, **kwargs: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Add a callable sink whose filter records every record it sees."""
    records: list[dict[str, Any]] = []
    lines: list[str] = []

    def keep(record: dict[str, Any]) -> bool:
        records.append(record)
        return True

    logger.add(lines.append, filter=keep, **kwargs)
    return records, lines


class TestPortedLoguruFilter:
    def test_level_no_and_time(self) -> None:
        logger = _new_logger()
        lines: list[str] = []
        logger.add(
            lines.append,
            format="{level}|{message}",
            filter=lambda r: r["level"].no >= 30 and r["time"].year > 2000,
        )

        logger.info("dropped")
        logger.warning("kept")
        logger.error("kept too")

        assert lines == ["WARNING|kept", "ERROR|kept too"]

    def test_filter_on_file_sink(self, tmp_path: Path) -> None:
        logger = _new_logger()
        path = tmp_path / "out.log"
        logger.add(
            path,
            format="{message}",
            filter=lambda r: r["level"].name == "ERROR" and r["exception"] is None,
        )

        logger.warning("no")
        logger.error("yes")
        logger.complete()

        assert path.read_text(encoding="utf-8").splitlines() == ["yes"]

    def test_common_loguru_accessors(self) -> None:
        logger = _new_logger()
        records, _ = _capture_filter(logger)

        logger.info("hello")

        record = records[-1]
        assert record["level"].name == "INFO"
        assert record["level"].no == 20
        assert record["level"].icon == "\u2139\ufe0f"
        assert record["file"].name == Path(__file__).name
        assert Path(record["file"].path).resolve() == Path(__file__).resolve()
        assert record["module"] == Path(__file__).stem
        assert record["name"] == __name__
        assert record["function"] == "test_common_loguru_accessors"
        assert record["thread"].id == threading.current_thread().ident
        assert record["thread"].name == threading.current_thread().name
        assert record["process"].id == os.getpid()
        assert record["process"].name == "MainProcess"
        assert record["exception"] is None


class TestBackwardCompat:
    def test_level_is_still_a_string(self) -> None:
        logger = _new_logger()
        records, _ = _capture_filter(logger)

        logger.info("hello")

        level = records[-1]["level"]
        assert isinstance(level, str)
        assert isinstance(level, RecordLevelStr)
        assert level == "INFO"
        assert level.lower() == "info"
        assert level in ("INFO", "ERROR")
        assert {"INFO": 1}[level] == 1
        assert json.dumps(level) == '"INFO"'
        assert f"{level:<8}|" == "INFO    |"
        assert repr(level) == "'INFO'"

    def test_flat_keys_are_kept(self) -> None:
        logger = _new_logger()
        records, _ = _capture_filter(logger)

        logger.info("hello")

        record = records[-1]
        assert record["level_no"] == 20
        assert record["file"] == Path(__file__).name
        assert isinstance(record["file"], RecordFile)
        assert record["thread_id"] == record["thread"].id
        assert record["thread_name"] == record["thread"].name
        assert record["process_id"] == record["process"].id
        assert record["process_name"] == record["process"].name
        assert isinstance(record["timestamp"], str)
        assert record["timestamp"][:19] == record["time"].isoformat()[:19]

    def test_elapsed_str_matches_previous_format(self) -> None:
        logger = _new_logger()
        records, _ = _capture_filter(logger)

        logger.info("hello")

        elapsed = records[-1]["elapsed"]
        assert isinstance(elapsed, datetime.timedelta)
        assert isinstance(elapsed, RecordElapsed)
        assert elapsed >= datetime.timedelta(0)
        assert _ELAPSED_RE.match(str(elapsed))
        assert f"{elapsed}" == str(elapsed)
        assert f"{elapsed:>15}" == str(elapsed).rjust(15)

    def test_elapsed_str_values(self) -> None:
        assert str(RecordElapsed(0)) == "00:00:00.000"
        assert str(RecordElapsed(seconds=3723, microseconds=456789)) == "01:02:03.456"
        assert str(RecordElapsed(days=1, seconds=1)) == "24:00:01.000"

    def test_exception_is_traceback_text(self) -> None:
        logger = _new_logger()
        records, _ = _capture_filter(logger)

        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("failed")

        exception = records[-1]["exception"]
        assert isinstance(exception, str)
        assert "ValueError: boom" in exception

    def test_time_is_aware(self) -> None:
        logger = _new_logger()
        records, _ = _capture_filter(logger)

        before = datetime.datetime.now(datetime.timezone.utc)
        logger.info("hello")
        after = datetime.datetime.now(datetime.timezone.utc)

        time = records[-1]["time"]
        assert type(time) is datetime.datetime
        assert time.tzinfo is not None
        assert (
            before - datetime.timedelta(seconds=1) <= time <= after + datetime.timedelta(seconds=1)
        )

    def test_filtered_callable_sink_output_unchanged(self) -> None:
        logger = _new_logger()
        lines: list[str] = []
        logger.add(
            lines.append,
            format="{level:<8}|{file}|{elapsed}|{message}",
            filter=lambda r: True,
        )

        logger.info("hello")

        level, file, elapsed, message = lines[-1].split("|")
        assert level == "INFO    "
        assert file == Path(__file__).name
        assert _ELAPSED_RE.match(elapsed)
        assert message == "hello"

    def test_filtered_serialized_callable_sink(self) -> None:
        logger = _new_logger()
        lines: list[str] = []
        logger.add(lines.append, serialize=True, filter=lambda r: r["level"].no >= 20)

        logger.debug("dropped")
        logger.info("hello")

        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["level"] == "INFO"
        assert data["message"] == "hello"


class TestCallbacks:
    def test_add_callback_gets_loguru_shape(self) -> None:
        logger = _new_logger()
        records: list[dict[str, Any]] = []
        logger.add_callback(records.append)

        logger.warning("hello")

        record = records[-1]
        assert record["level"] == "WARNING"
        assert record["level"].no == 30
        assert isinstance(record["time"], datetime.datetime)
        assert isinstance(record["thread"], RecordThread)
        assert isinstance(record["process"], RecordProcess)


class TestCustomLevels:
    def test_custom_level_shape(self) -> None:
        logger = _new_logger()
        logger.level("RECCOMPAT", no=27, icon="*")
        records, _ = _capture_filter(logger)

        logger.log("RECCOMPAT", "custom")

        record = records[-1]
        assert record["level"] == "RECCOMPAT"
        assert record["level"].no == 27
        assert record["level"].icon == "*"
        assert record["level_no"] == 27
        assert isinstance(record["time"], datetime.datetime)
        assert record["exception"] is None

    def test_icon_update_is_seen(self) -> None:
        logger = _new_logger()
        logger.level("RECCOMPAT2", no=26, icon="a")
        records, _ = _capture_filter(logger)

        logger.log("RECCOMPAT2", "first")
        logger.level("RECCOMPAT2", icon="b")
        logger.log("RECCOMPAT2", "second")

        assert records[0]["level"].icon == "a"
        assert records[1]["level"].icon == "b"


class TestPatchers:
    def test_patcher_record_shape(self) -> None:
        logger = _new_logger()
        seen: list[dict[str, Any]] = []
        lines: list[str] = []
        logger.add(lines.append, format="{message}")

        logger.patch(seen.append).error("hello")

        record = seen[-1]
        assert record["level"] == "ERROR"
        assert record["level"].no == 40
        assert record["level_no"] == 40
        assert isinstance(record["time"], datetime.datetime)
        assert record["time"].tzinfo is not None
        assert isinstance(record["timestamp"], str)
        assert record["thread"].id == threading.current_thread().ident
        assert record["process"].id == os.getpid()
        assert record["exception"] is None

    def test_patcher_changes_propagate(self) -> None:
        logger = _new_logger()
        lines: list[str] = []
        logger.add(lines.append, format="{message}|{extra[tag]}")

        def patch(record: dict[str, Any]) -> None:
            if record["level"].no >= 30:
                record["message"] = record["message"].upper()
            record["extra"]["tag"] = record["level"].name.lower()

        patched = logger.patch(patch)
        patched.info("quiet")
        patched.warning("loud")

        assert lines == ["quiet|info", "LOUD|warning"]

    def test_patcher_exception_propagates(self) -> None:
        logger = _new_logger()
        records, _ = _capture_filter(logger)

        def patch(record: dict[str, Any]) -> None:
            record["exception"] = "patched traceback"

        logger.patch(patch).info("hello")

        assert records[-1]["exception"] == "patched traceback"


class TestValues:
    @pytest.mark.parametrize(
        "value",
        [
            RecordLevelStr("INFO", 20, "i"),
            RecordFile("a.py", "/x/a.py"),
            RecordElapsed(seconds=5),
        ],
    )
    def test_pickle_roundtrip(self, value: object) -> None:
        copy = pickle.loads(pickle.dumps(value))
        assert copy == value
        assert type(copy) is type(value)
        for attr in ("name", "no", "icon", "path"):
            if hasattr(value, attr):
                assert getattr(copy, attr) == getattr(value, attr)

    def test_thread_and_process_format(self) -> None:
        thread = RecordThread(123, "Worker")
        process = RecordProcess(456, "Main")
        assert f"{thread}" == "123"
        assert f"{process:>5}" == "  456"
        assert repr(thread) == "(id=123, name='Worker')"
        assert thread == RecordThread(123, "Worker")

    def test_records_are_cached_but_independent(self) -> None:
        logger = _new_logger()
        records, _ = _capture_filter(logger)
        logger.info("x")
        logger.info("y")
        assert records[0]["level"] is records[1]["level"]
        assert records[0] is not records[1]
