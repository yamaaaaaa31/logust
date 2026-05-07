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


def test_string_passthrough_in_json(tmp_path: Path) -> None:
    """String extras must remain strings (not double-quoted) in JSON."""
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "string.json"
    logger.add(log_file, serialize=True)

    logger.info("hi", user="alice", path="/api/v1")
    logger.complete()

    record = json.loads(log_file.read_text())
    assert record["extra"] == {"user": "alice", "path": "/api/v1"}


def test_bool_distinct_from_int_in_json(tmp_path: Path) -> None:
    """``True`` must serialize as ``true``, not ``1`` (bool is subclass of int)."""
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "bool.json"
    logger.add(log_file, serialize=True)

    logger.info("flags", enabled=True, disabled=False, count=1)
    logger.complete()

    raw = log_file.read_text()
    record = json.loads(raw)
    assert record["extra"]["enabled"] is True
    assert record["extra"]["disabled"] is False
    assert record["extra"]["count"] == 1
    assert isinstance(record["extra"]["count"], int)
    # Verify the raw JSON tokens to guard against bool/int conflation.
    assert '"enabled":true' in raw.replace(" ", "")
    assert '"disabled":false' in raw.replace(" ", "")


def test_deeply_nested_dict_in_json(tmp_path: Path) -> None:
    """Three-level nested structures must round-trip with native types."""
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "nested.json"
    logger.add(log_file, serialize=True)

    logger.info(
        "nested",
        meta={
            "user": {"id": 7, "tags": ["admin", "ops"]},
            "trace": {"span": {"id": "abc", "depth": 3}},
        },
    )
    logger.complete()

    record = json.loads(log_file.read_text())
    assert record["extra"]["meta"]["user"]["id"] == 7
    assert record["extra"]["meta"]["user"]["tags"] == ["admin", "ops"]
    assert record["extra"]["meta"]["trace"]["span"]["depth"] == 3


def test_tuple_serializes_as_array(tmp_path: Path) -> None:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "tuple.json"
    logger.add(log_file, serialize=True)

    logger.info("t", coords=(1, 2, 3))
    logger.complete()

    record = json.loads(log_file.read_text())
    assert record["extra"]["coords"] == [1, 2, 3]


def test_big_int_falls_back_to_string(tmp_path: Path) -> None:
    """Integers outside ``i64`` / ``u64`` range fall back to a string."""
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "big.json"
    logger.add(log_file, serialize=True)

    big = 2**100
    logger.info("big", n=big)
    logger.complete()

    record = json.loads(log_file.read_text())
    assert record["extra"]["n"] == str(big)


def test_nan_and_inf_fall_back_to_string(tmp_path: Path) -> None:
    """``NaN`` / ``Inf`` are not valid JSON numbers, so they stringify."""
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "nan.json"
    logger.add(log_file, serialize=True)

    nan = float("nan")
    inf = float("inf")
    logger.info("special", nan=nan, inf=inf)
    logger.complete()

    record = json.loads(log_file.read_text())
    assert record["extra"]["nan"] == "nan"
    assert record["extra"]["inf"] == "inf"


def test_recursive_structure_does_not_crash(tmp_path: Path) -> None:
    """Cyclic data must not stack-overflow; sentinel string is acceptable."""
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "cycle.json"
    logger.add(log_file, serialize=True)

    cyclic: dict[str, Any] = {"name": "root"}
    cyclic["self"] = cyclic

    logger.info("cycle", data=cyclic)
    logger.complete()

    raw = log_file.read_text()
    # Whatever the strategy, the file must be valid JSON and contain the sentinel.
    record = json.loads(raw)
    assert "<recursion limit reached>" in raw
    assert record["extra"]["data"]["name"] == "root"


def test_extra_format_token_renders_as_string(tmp_path: Path) -> None:
    """``{extra[key]}`` in format templates must keep stringified output."""
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "fmt.log"
    logger.add(log_file, format="{extra[count]}|{extra[ok]}|{message}")

    logger.info("done", count=42, ok=True)
    logger.complete()

    text = log_file.read_text().strip()
    assert text == "42|True|done"
