"""Tests for typed extra values in JSON output."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import Enum, IntEnum
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from logust._logger import Logger
from logust._logust import LogLevel, PyLogger


def _json_extra(tmp_path: Path, filename: str, **extra: Any) -> dict[str, Any]:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()

    log_file = tmp_path / filename
    logger.add(log_file, serialize=True)

    logger.info("typed", **extra)
    logger.complete()

    return json.loads(log_file.read_text(encoding="utf-8"))["extra"]


def _text_callback_and_json_extra(
    tmp_path: Path, key: str, value: Any
) -> tuple[str, Any, dict[str, Any]]:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()

    text_file = tmp_path / f"{key}.log"
    json_file = tmp_path / f"{key}.json"
    records: list[dict[str, Any]] = []
    logger.add(text_file, format=f"{{extra[{key}]}}|{{message}}")
    logger.add_callback(records.append, level=LogLevel.Trace)
    logger.add(json_file, serialize=True)

    logger.info("typed", **{key: value})
    logger.complete()

    text = text_file.read_text(encoding="utf-8").strip()
    json_extra = json.loads(json_file.read_text(encoding="utf-8"))["extra"]
    return text, records[0]["extra"][key], json_extra


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

    record = json.loads(log_file.read_text(encoding="utf-8"))
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


def test_serialized_callable_sink_receives_typed_extra_values() -> None:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    messages: list[str] = []
    logger.add(messages.append, level=LogLevel.Trace, serialize=True)

    logger.info(
        "typed",
        status_code=201,
        ok=True,
        ratio=0.5,
        tags=["a", 1],
        meta={"k": False},
        missing=None,
        body=b"hi",
    )

    record = json.loads(messages[0])
    assert record["extra"] == {
        "status_code": 201,
        "ok": True,
        "ratio": 0.5,
        "tags": ["a", 1],
        "meta": {"k": False},
        "missing": None,
        "body": "hi",
    }


def test_serialized_callable_sink_filter_sees_text_view() -> None:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    messages: list[str] = []
    seen_by_filter: list[Any] = []

    def keep_201(record: dict[str, Any]) -> bool:
        seen_by_filter.append(record["extra"]["status_code"])
        return record["extra"]["status_code"] == "201"

    logger.add(messages.append, level=LogLevel.Trace, serialize=True, filter=keep_201)
    logger.info("typed", status_code=201)
    logger.info("typed", status_code=500)

    assert seen_by_filter == ["201", "500"]
    assert len(messages) == 1
    assert json.loads(messages[0])["extra"] == {"status_code": "201"}


def test_non_serialized_callable_sink_filter_keeps_string_extra_values() -> None:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    messages: list[str] = []
    records: list[dict[str, Any]] = []

    def capture(record: dict[str, Any]) -> bool:
        records.append(record)
        return True

    logger.add(messages.append, level=LogLevel.Trace, format="{message}", filter=capture)
    logger.info(
        "typed",
        status_code=201,
        ok=True,
        tags=["a", 1],
        meta={"k": False},
        missing=None,
        body=b"hi",
    )

    assert messages == ["typed"]
    assert records[0]["extra"] == {
        "status_code": "201",
        "ok": "True",
        "tags": "['a', 1]",
        "meta": "{'k': False}",
        "missing": "None",
        "body": "b'hi'",
    }


def test_string_passthrough_in_json(tmp_path: Path) -> None:
    """String extras must remain strings (not double-quoted) in JSON."""
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "string.json"
    logger.add(log_file, serialize=True)

    logger.info("hi", user="alice", path="/api/v1")
    logger.complete()

    record = json.loads(log_file.read_text(encoding="utf-8"))
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

    raw = log_file.read_text(encoding="utf-8")
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

    record = json.loads(log_file.read_text(encoding="utf-8"))
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

    record = json.loads(log_file.read_text(encoding="utf-8"))
    assert record["extra"]["coords"] == [1, 2, 3]


def test_bytes_utf8_decoded_in_json(tmp_path: Path) -> None:
    extra = _json_extra(tmp_path, "bytes.json", body=b"hello")

    assert extra["body"] == "hello"


def test_bytearray_utf8_decoded_in_json(tmp_path: Path) -> None:
    extra = _json_extra(tmp_path, "bytearray.json", body=bytearray(b"hello"))

    assert extra["body"] == "hello"


def test_bytes_with_invalid_utf8_uses_replacement(tmp_path: Path) -> None:
    extra = _json_extra(tmp_path, "bytes-invalid.json", body=b"hi\xffthere")

    assert extra["body"] == "hi\ufffdthere"


def test_bytearray_with_invalid_utf8_uses_replacement(tmp_path: Path) -> None:
    extra = _json_extra(tmp_path, "bytearray-invalid.json", body=bytearray(b"hi\xffthere"))

    assert extra["body"] == "hi\ufffdthere"


def test_set_serializes_as_array(tmp_path: Path) -> None:
    extra = _json_extra(tmp_path, "set.json", values={3, 1, 2})

    assert sorted(extra["values"]) == [1, 2, 3]


def test_frozenset_serializes_as_array(tmp_path: Path) -> None:
    extra = _json_extra(tmp_path, "frozenset.json", values=frozenset({3, 1, 2}))

    assert sorted(extra["values"]) == [1, 2, 3]


def test_datetime_uses_isoformat(tmp_path: Path) -> None:
    extra = _json_extra(
        tmp_path,
        "datetime.json",
        when=datetime(2026, 5, 7, 12, 34, 56),
    )

    assert extra["when"] == "2026-05-07T12:34:56"


def test_date_uses_isoformat(tmp_path: Path) -> None:
    extra = _json_extra(tmp_path, "date.json", when=date(2026, 5, 7))

    assert extra["when"] == "2026-05-07"


def test_time_uses_isoformat(tmp_path: Path) -> None:
    extra = _json_extra(tmp_path, "time.json", when=time(12, 34, 56, 789))

    assert extra["when"] == "12:34:56.000789"


def test_aware_datetime_includes_timezone(tmp_path: Path) -> None:
    extra = _json_extra(
        tmp_path,
        "datetime-aware.json",
        when=datetime(2026, 5, 7, 12, 34, 56, tzinfo=timezone(timedelta(hours=9))),
    )

    assert extra["when"] == "2026-05-07T12:34:56+09:00"


def test_nested_set_in_dict(tmp_path: Path) -> None:
    extra = _json_extra(tmp_path, "nested-set.json", payload={"roles": {"ops", "admin"}})

    assert sorted(extra["payload"]["roles"]) == ["admin", "ops"]


def test_extended_types_inside_nested_containers(tmp_path: Path) -> None:
    class Kind(Enum):
        FILE = "file"

    extra = _json_extra(
        tmp_path,
        "nested-extended.json",
        payload={
            "body": [b"hello", bytearray(b"bye")],
            "timestamps": [
                datetime(2026, 5, 7, 12, 34, 56),
                date(2026, 5, 7),
                time(12, 34, 56),
            ],
            "kind": Kind.FILE,
        },
    )

    assert extra["payload"] == {
        "body": ["hello", "bye"],
        "timestamps": ["2026-05-07T12:34:56", "2026-05-07", "12:34:56"],
        "kind": "file",
    }


def test_enum_serializes_value_in_json(tmp_path: Path) -> None:
    class Status(Enum):
        OK = "ok"

    extra = _json_extra(tmp_path, "enum.json", status=Status.OK)

    assert extra["status"] == "ok"


def test_enum_value_uses_typed_json_conversion(tmp_path: Path) -> None:
    class Payload(Enum):
        ROLES = frozenset({"ops", "admin"})

    extra = _json_extra(tmp_path, "enum-payload.json", payload=Payload.ROLES)

    assert sorted(extra["payload"]) == ["admin", "ops"]


def test_int_enum_and_str_enum_use_values_in_json(tmp_path: Path) -> None:
    class Code(IntEnum):
        CREATED = 201

    class Action(str, Enum):
        LOGIN = "login"

    extra = _json_extra(tmp_path, "enum-fast-paths.json", code=Code.CREATED, action=Action.LOGIN)

    assert extra == {"code": 201, "action": "login"}


def test_str_subclass_text_uses_python_str_and_json_uses_underlying_value(
    tmp_path: Path,
) -> None:
    class S(str):
        def __str__(self) -> str:
            return "custom"

    text, callback_value, extra = _text_callback_and_json_extra(tmp_path, "s", S("raw"))

    assert text == "custom|typed"
    assert callback_value == "custom"
    assert extra["s"] == "raw"


def test_int_enum_text_uses_python_str_and_json_uses_underlying_value(
    tmp_path: Path,
) -> None:
    class Code(IntEnum):
        CREATED = 201

        def __str__(self) -> str:
            return "Code.CREATED"

    text, callback_value, extra = _text_callback_and_json_extra(tmp_path, "code", Code.CREATED)

    assert text == "Code.CREATED|typed"
    assert callback_value == "Code.CREATED"
    assert extra["code"] == 201


def test_str_enum_text_uses_python_str_and_json_uses_underlying_value(
    tmp_path: Path,
) -> None:
    class Action(str, Enum):
        LOGIN = "login"

    text, callback_value, extra = _text_callback_and_json_extra(tmp_path, "action", Action.LOGIN)

    assert text == "Action.LOGIN|typed"
    assert callback_value == "Action.LOGIN"
    assert extra["action"] == "login"


def test_int_subclass_text_uses_python_str_and_json_uses_underlying_value(
    tmp_path: Path,
) -> None:
    class IntSubclass(int):
        def __str__(self) -> str:
            return "I-custom"

    text, callback_value, extra = _text_callback_and_json_extra(tmp_path, "i", IntSubclass(7))

    assert text == "I-custom|typed"
    assert callback_value == "I-custom"
    assert extra["i"] == 7


def test_text_view_unchanged_for_enum(tmp_path: Path) -> None:
    class Status(Enum):
        OK = "ok"

    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()

    text_file = tmp_path / "enum.log"
    json_file = tmp_path / "enum.json"
    logger.add(text_file, format="{extra[status]}|{message}")
    logger.add(json_file, serialize=True)

    logger.info("enum", status=Status.OK)
    logger.complete()

    assert text_file.read_text(encoding="utf-8").strip() == "Status.OK|enum"
    record = json.loads(json_file.read_text(encoding="utf-8"))
    assert record["extra"]["status"] == "ok"


def test_top_level_failing_str_does_not_crash_log(tmp_path: Path) -> None:
    class BadStr:
        def __repr__(self) -> str:
            return "BadStr-repr"

        def __str__(self) -> str:
            raise RuntimeError("bad str")

    extra = _json_extra(tmp_path, "bad-str-direct.json", obj=BadStr())

    assert extra["obj"] == "BadStr-repr"


def test_failing_str_inside_container_falls_back_to_text_view(tmp_path: Path) -> None:
    class BadStr:
        def __repr__(self) -> str:
            return "BadStr"

        def __str__(self) -> str:
            raise RuntimeError("bad str")

    extra = _json_extra(tmp_path, "bad-str.json", payload=[BadStr()])

    assert extra["payload"] == "[BadStr]"


def test_object_with_value_attribute_is_not_treated_as_enum(tmp_path: Path) -> None:
    class HasValue:
        value = "not-an-enum"

        def __str__(self) -> str:
            return "HasValue(custom)"

    extra = _json_extra(tmp_path, "value-attribute.json", custom=HasValue())

    assert extra["custom"] == "HasValue(custom)"


def test_text_view_unchanged_for_datetime(tmp_path: Path) -> None:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()

    text_file = tmp_path / "datetime.log"
    json_file = tmp_path / "datetime.json"
    logger.add(text_file, format="{extra[when]}|{message}")
    logger.add(json_file, serialize=True)

    logger.info("dt", when=datetime(2026, 5, 7, 0, 0, 0))
    logger.complete()

    assert text_file.read_text(encoding="utf-8").strip() == "2026-05-07 00:00:00|dt"
    record = json.loads(json_file.read_text(encoding="utf-8"))
    assert record["extra"]["when"] == "2026-05-07T00:00:00"


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

    record = json.loads(log_file.read_text(encoding="utf-8"))
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

    record = json.loads(log_file.read_text(encoding="utf-8"))
    assert record["extra"]["nan"] == "nan"
    assert record["extra"]["inf"] == "inf"


def test_documented_fallthrough_types_remain_strings(tmp_path: Path) -> None:
    request_id = UUID("12345678-1234-5678-1234-567812345678")
    path = Path("/tmp/logust")

    extra = _json_extra(
        tmp_path,
        "fallthrough.json",
        amount=Decimal("1.50"),
        request_id=request_id,
        path=path,
        z=1 + 2j,
    )

    assert extra == {
        "amount": "1.50",
        "request_id": str(request_id),
        "path": str(path),
        "z": "(1+2j)",
    }


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

    raw = log_file.read_text(encoding="utf-8")
    # Whatever the strategy, the file must be valid JSON and contain the sentinel.
    record = json.loads(raw)
    assert "<recursion limit reached>" in raw
    assert record["extra"]["data"]["name"] == "root"


def test_repeated_backreferences_stop_at_container_identity(tmp_path: Path) -> None:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "shared-cycle.json"
    logger.add(log_file, serialize=True)

    cyclic: dict[str, Any] = {}
    cyclic["a"] = cyclic
    cyclic["b"] = cyclic

    start = perf_counter()
    logger.info("cycle", data=cyclic)
    logger.complete()
    elapsed = perf_counter() - start

    raw = log_file.read_text(encoding="utf-8")
    record = json.loads(raw)
    sentinel = "<recursion limit reached>"
    assert elapsed < 2.0
    assert raw.count(sentinel) == 2
    assert record["extra"]["data"] == {"a": sentinel, "b": sentinel}


def test_self_referential_list_uses_sentinel(tmp_path: Path) -> None:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "list-cycle.json"
    logger.add(log_file, serialize=True)

    cyclic: list[Any] = []
    cyclic.append(cyclic)

    start = perf_counter()
    logger.info("cycle", data=cyclic)
    logger.complete()
    elapsed = perf_counter() - start

    record = json.loads(log_file.read_text(encoding="utf-8"))
    assert elapsed < 2.0
    assert record["extra"]["data"] == ["<recursion limit reached>"]


def test_cross_container_cycle_uses_sentinel(tmp_path: Path) -> None:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "cross-cycle.json"
    logger.add(log_file, serialize=True)

    a: dict[str, Any] = {}
    b: list[Any] = [a]
    a["b"] = b

    start = perf_counter()
    logger.info("cycle", data=a)
    logger.complete()
    elapsed = perf_counter() - start

    record = json.loads(log_file.read_text(encoding="utf-8"))
    assert elapsed < 2.0
    assert record["extra"]["data"] == {"b": ["<recursion limit reached>"]}


def test_extra_format_token_renders_as_string(tmp_path: Path) -> None:
    """``{extra[key]}`` in format templates must keep stringified output."""
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    log_file = tmp_path / "fmt.log"
    logger.add(log_file, format="{extra[count]}|{extra[ok]}|{message}")

    logger.info("done", count=42, ok=True)
    logger.complete()

    text = log_file.read_text(encoding="utf-8").strip()
    assert text == "42|True|done"
