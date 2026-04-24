"""Tests for loguru-style kwargs formatting and per-call extra."""

from __future__ import annotations

from typing import Any

import pytest

from logust._logger import Logger
from logust._logust import LogLevel, PyLogger


def make_logger() -> tuple[Logger, list[dict[str, Any]]]:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()

    records: list[dict[str, Any]] = []

    def capture(record: dict[str, Any]) -> None:
        snapshot = record.copy()
        snapshot["extra"] = dict(record.get("extra", {}))
        records.append(snapshot)

    logger.add_callback(capture, level=LogLevel.Trace)
    return logger, records


class ExplodingFormat:
    def __format__(self, format_spec: str) -> str:
        raise AssertionError("message formatting should have been skipped")


def test_message_with_braces_without_kwargs_remains_literal() -> None:
    logger, records = make_logger()

    logger.info("braces {unused}")

    assert len(records) == 1
    assert records[0]["message"] == "braces {unused}"
    assert records[0]["extra"] == {}


def test_positional_placeholder_without_kwargs_remains_literal() -> None:
    logger, records = make_logger()

    logger.info("{0}")

    assert len(records) == 1
    assert records[0]["message"] == "{0}"
    assert records[0]["extra"] == {}


def test_kwargs_without_placeholder_become_extra() -> None:
    logger, records = make_logger()

    logger.info("msg", k="v")

    assert len(records) == 1
    assert records[0]["message"] == "msg"
    assert records[0]["extra"] == {"k": "v"}


def test_kwargs_consumed_by_format_are_not_extra() -> None:
    logger, records = make_logger()

    logger.info("{k}", k="v")

    assert len(records) == 1
    assert records[0]["message"] == "v"
    assert records[0]["extra"] == {}


def test_attribute_access_consumes_root_kwarg() -> None:
    logger, records = make_logger()
    user = type("User", (), {"name": "a"})()

    logger.info("{u.name}", u=user)

    assert len(records) == 1
    assert records[0]["message"] == "a"
    assert records[0]["extra"] == {}


def test_item_access_consumes_root_kwarg() -> None:
    logger, records = make_logger()

    logger.info("{d[k]}", d={"k": "v"})

    assert len(records) == 1
    assert records[0]["message"] == "v"
    assert records[0]["extra"] == {}


def test_nested_format_spec_consumes_value_and_spec_kwargs() -> None:
    logger, records = make_logger()

    logger.info("{x:{width}}", x=5, width=3)

    assert len(records) == 1
    assert records[0]["message"] == "  5"
    assert records[0]["extra"] == {}


def test_conversion_consumes_root_kwarg() -> None:
    logger, records = make_logger()

    logger.info("{x!r}", x="v")

    assert len(records) == 1
    assert records[0]["message"] == "'v'"
    assert records[0]["extra"] == {}


def test_numeric_prefixed_kwarg_is_not_treated_as_positional() -> None:
    logger, records = make_logger()

    logger.info("{0abc}", **{"0abc": "v"})

    assert len(records) == 1
    assert records[0]["message"] == "v"
    assert records[0]["extra"] == {}


def test_kwargs_can_format_message_and_fill_extra() -> None:
    logger, records = make_logger()

    logger.info("{a}", a=1, b=2)

    assert len(records) == 1
    assert records[0]["message"] == "1"
    assert records[0]["extra"] == {"b": "2"}


def test_missing_placeholder_without_kwargs_remains_literal() -> None:
    logger, records = make_logger()

    logger.info("{missing}")

    assert len(records) == 1
    assert records[0]["message"] == "{missing}"
    assert records[0]["extra"] == {}


def test_missing_format_kwarg_raises_key_error() -> None:
    logger, records = make_logger()

    with pytest.raises(KeyError):
        logger.info("{missing}", present="value")

    assert records == []


def test_non_str_message_with_kwargs_is_coerced() -> None:
    """Non-str messages must still work when kwargs are passed (parity with
    the no-kwargs path which already wraps message with str())."""
    logger, records = make_logger()

    logger.info(42, note="life")  # type: ignore[arg-type]

    assert len(records) == 1
    assert records[0]["message"] == "42"
    assert records[0]["extra"] == {"note": "life"}


def test_bound_and_per_call_extra_are_merged() -> None:
    logger, records = make_logger()

    logger.bind(x=1).info("y", z=2)

    assert len(records) == 1
    assert records[0]["message"] == "y"
    assert records[0]["extra"] == {"x": "1", "z": "2"}


def test_per_call_extra_overrides_bound_key() -> None:
    logger, records = make_logger()

    logger.bind(x=1).info("y", x=2)

    assert len(records) == 1
    assert records[0]["message"] == "y"
    assert records[0]["extra"] == {"x": "2"}


def test_callable_sink_can_render_extra_by_key() -> None:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()

    messages: list[str] = []
    logger.add(messages.append, format="{level} | {message} | session={extra[session]}")

    logger.info("user {id} did {action}", id=42, action="login", session="abc")

    assert messages == ["INFO | user 42 did login | session=abc"]


def test_disabled_levels_skip_kwargs_formatting() -> None:
    inner = PyLogger(LogLevel.Warning)
    logger = Logger(inner)
    logger.disable()
    records: list[dict[str, Any]] = []
    logger.add_callback(records.append, level=LogLevel.Warning)
    logger.level("VERBOSE_REVIEW", no=15)

    logger.debug("{bad}", bad=ExplodingFormat())
    logger.log("DEBUG", "{bad}", bad=ExplodingFormat())
    logger.log("VERBOSE_REVIEW", "{bad}", bad=ExplodingFormat())

    assert records == []


def test_all_levels_support_kwargs_extra_smoke() -> None:
    logger, records = make_logger()
    logger.level("NOTICE", no=26)

    emitters = [
        ("TRACE", "trace", lambda: logger.trace("trace {value}", value="trace", marker="trace")),
        ("DEBUG", "debug", lambda: logger.debug("debug {value}", value="debug", marker="debug")),
        ("INFO", "info", lambda: logger.info("info {value}", value="info", marker="info")),
        (
            "SUCCESS",
            "success",
            lambda: logger.success("success {value}", value="success", marker="success"),
        ),
        (
            "WARNING",
            "warning",
            lambda: logger.warning("warning {value}", value="warning", marker="warning"),
        ),
        ("ERROR", "error", lambda: logger.error("error {value}", value="error", marker="error")),
        ("FAIL", "fail", lambda: logger.fail("fail {value}", value="fail", marker="fail")),
        (
            "CRITICAL",
            "critical",
            lambda: logger.critical("critical {value}", value="critical", marker="critical"),
        ),
        ("NOTICE", "log", lambda: logger.log("NOTICE", "log {value}", value="log", marker="log")),
    ]

    for _, _, emit in emitters:
        emit()

    assert len(records) == len(emitters)
    for record, (level, value, _) in zip(records, emitters, strict=True):
        assert record["level"] == level
        assert record["message"] == f"{value} {value}"
        assert record["extra"] == {"marker": value}
