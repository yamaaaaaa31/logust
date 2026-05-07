"""Tests for typed extra values in JSON output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from logust._logger import Logger
from logust._logust import LogLevel, PyLogger


def test_json_file_preserves_extra_value_types(tmp_path: Path) -> None:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()

    log_file = tmp_path / "typed.json"
    logger.add(log_file, serialize=True)

    logger.info(
        "typed",
        status_code=201,
        duration_ms=12.5,
        ok=True,
        tags=["checkout", 2],
        meta={"attempt": 1, "cached": False},
        missing=None,
    )
    logger.complete()

    record = json.loads(log_file.read_text())
    assert record["message"] == "typed"
    assert record["extra"] == {
        "status_code": 201,
        "duration_ms": 12.5,
        "ok": True,
        "tags": ["checkout", 2],
        "meta": {"attempt": 1, "cached": False},
        "missing": None,
    }


def test_callback_extra_values_remain_string_compatible() -> None:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    records: list[dict[str, Any]] = []
    logger.add_callback(records.append, level=LogLevel.Trace)

    logger.info("typed", status_code=201, ok=True)

    assert records[0]["extra"] == {"status_code": "201", "ok": "True"}
