"""Tests for loguru-style positional-argument message formatting."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

import logust
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


def test_positional_args_format_message() -> None:
    logger, records = make_logger()

    logger.info("x {} y {}", 1, "two")

    assert records[0]["message"] == "x 1 y two"
    assert records[0]["extra"] == {}


def test_indexed_positional_args() -> None:
    logger, records = make_logger()

    logger.info("{1}-{0}", "a", "b")

    assert records[0]["message"] == "b-a"


def test_mixed_positional_and_kwargs() -> None:
    logger, records = make_logger()

    logger.info("{} by {user}", "login", user="alice", request_id="r1")

    assert records[0]["message"] == "login by alice"
    assert records[0]["extra"] == {"request_id": "r1"}


def test_braces_without_args_remain_literal() -> None:
    logger, records = make_logger()

    logger.info("dict {} and {0} and {name}")

    assert records[0]["message"] == "dict {} and {0} and {name}"


def test_escaped_braces_with_args() -> None:
    logger, records = make_logger()

    logger.info("{{literal}} {}", 1)

    assert records[0]["message"] == "{literal} 1"


def test_missing_positional_arg_raises_index_error() -> None:
    logger, records = make_logger()

    with pytest.raises(IndexError):
        logger.info("{} {}", 1)

    assert records == []


def test_missing_kwarg_with_positional_raises_key_error() -> None:
    logger, records = make_logger()

    with pytest.raises(KeyError):
        logger.info("{} {missing}", 1)

    assert records == []


def test_non_str_message_with_args_is_coerced() -> None:
    logger, records = make_logger()

    logger.info(123, "ignored")

    assert records[0]["message"] == "123"


def test_disabled_levels_skip_positional_formatting() -> None:
    inner = PyLogger(LogLevel.Warning)
    logger = Logger(inner)
    logger.disable()
    records: list[dict[str, Any]] = []
    logger.add_callback(records.append, level=LogLevel.Warning)
    logger.level("VERBOSE_REVIEW", no=15)

    logger.debug("{}", ExplodingFormat())
    logger.log("DEBUG", "{}", ExplodingFormat())
    logger.log(10, "{}", ExplodingFormat())
    logger.log("VERBOSE_REVIEW", "{}", ExplodingFormat())

    assert records == []


def test_all_levels_support_positional_args() -> None:
    logger, records = make_logger()
    logger.level("NOTICE", no=26)

    logger.trace("t {}", 1)
    logger.debug("d {}", 2)
    logger.info("i {}", 3)
    logger.success("s {}", 4)
    logger.warning("w {}", 5)
    logger.error("e {}", 6)
    logger.fail("f {}", 7)
    logger.critical("c {}", 8)
    logger.log("INFO", "l {}", 9)
    logger.log(20, "n {}", 10)
    logger.log("NOTICE", "custom {}", 11)

    assert [r["message"] for r in records] == [
        "t 1",
        "d 2",
        "i 3",
        "s 4",
        "w 5",
        "e 6",
        "f 7",
        "c 8",
        "l 9",
        "n 10",
        "custom 11",
    ]
    assert records[-1]["level"] == "NOTICE"


def test_exception_supports_positional_args() -> None:
    logger, records = make_logger()

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed {} times", 3)

    assert records[0]["level"] == "ERROR"
    assert records[0]["message"] == "failed 3 times"
    assert "ValueError: boom" in (records[0]["exception"] or "")


def test_caller_line_is_correct_with_positional_args() -> None:
    logger, _ = make_logger()
    messages: list[str] = []
    logger.add(messages.append, format="{function}:{line} - {message}")

    line = inspect.currentframe().f_lineno + 1  # type: ignore[union-attr]
    logger.info("value {}", 42)
    logger.opt().info("opt {}", 7)
    opt_line = line + 1

    assert messages == [
        f"test_caller_line_is_correct_with_positional_args:{line} - value 42",
        f"test_caller_line_is_correct_with_positional_args:{opt_line} - opt 7",
    ]


def test_opt_mixed_positional_and_kwargs_formats_once() -> None:
    logger, records = make_logger()

    logger.opt().info("{} by {user}", "{not-a-field}", user="bob", tag="t")
    logger.opt(lazy=True).info("lazy {} {user}", lambda: "v", user="amy")

    assert records[0]["message"] == "{not-a-field} by bob"
    assert records[0]["extra"] == {"tag": "t"}
    assert records[1]["message"] == "lazy v amy"


def test_module_level_functions_accept_positional_args() -> None:
    records: list[dict[str, Any]] = []
    callback_id = logust.logger.add_callback(records.append, level=LogLevel.Trace)
    try:
        logust.info("module {}", 1)
        logust.logger.info("logger {} {k}", 2, k=3)
    finally:
        logust.logger.remove_callback(callback_id)

    assert [r["message"] for r in records] == ["module 1", "logger 2 3"]
