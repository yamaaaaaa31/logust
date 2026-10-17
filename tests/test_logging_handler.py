"""Standard logging must use the target logger's patchers and exception options."""

from __future__ import annotations

import logging
import sys
from collections.abc import Generator
from typing import Any

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger
from logust.contrib.logging_handler import InterceptHandler


@pytest.fixture
def logger() -> Generator[Logger, None, None]:
    target = Logger(PyLogger(LogLevel.Trace))
    target.remove()
    yield target
    target.remove()


def record(message: str = "token=%s", *args: Any) -> logging.LogRecord:
    return logging.LogRecord(
        "thirdparty.client", logging.INFO, __file__, 123, message, args, None, func="original"
    )


def test_intercepted_records_run_configured_and_chained_patchers(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message} {extra[tag]}")
    order: list[str] = []

    def redact(item: dict[str, Any]) -> None:
        order.append("redact")
        item["message"] = item["message"].replace("secret", "REDACTED")

    def tag(item: dict[str, Any]) -> None:
        order.append("tag")
        item["extra"]["tag"] = "patched"

    logger.configure(patcher=redact)
    target = logger.bind(tag="bound").patch(tag)
    with logger.contextualize(tag="context"):
        InterceptHandler(target).emit(record("token=%s {literal}", "secret"))

    assert messages == ["token=REDACTED {literal} patched"]
    assert order == ["redact", "tag"]


def test_intercepted_patcher_exception_replacement_is_used(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message}|{exception}", diagnose=True)

    def redact(item: dict[str, Any]) -> None:
        item["exception"] = "redacted traceback"

    event = record("failed")
    try:
        raise ValueError("secret")
    except ValueError:
        event.exc_info = sys.exc_info()
        InterceptHandler(logger.patch(redact)).emit(event)

    assert messages == ["failed|redacted traceback"]


def test_intercepted_context_and_bound_values_reach_patchers_and_sinks(logger: Logger) -> None:
    records: list[dict[str, Any]] = []
    logger.add_callback(records.append)
    seen: list[dict[str, Any]] = []

    def patch(item: dict[str, Any]) -> None:
        seen.append(item["extra"].copy())
        item["extra"]["patch"] = "yes"

    target = logger.bind(overlap="bound").patch(patch)
    with logger.contextualize(context="yes", overlap="context"):
        InterceptHandler(target).emit(record("context"))

    assert seen == [{"context": "yes", "overlap": "bound"}]
    assert records[0]["extra"] == {"context": "yes", "overlap": "bound", "patch": "yes"}
    # The integration still has no caller metadata; do not report this module
    # or the handler as the stdlib caller.
    assert records[0]["name"] == ""
    assert records[0]["function"] == ""
    assert records[0]["line"] == 0


def test_intercepted_context_without_patchers(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{extra[context]} {extra[overlap]}")
    with logger.contextualize(context="yes", overlap="context"):
        InterceptHandler(logger.bind(overlap="bound")).emit(record("context"))
    assert messages == ["yes bound"]


def test_interception_matches_activation_against_stdlib_name(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message}")
    logger.disable(__name__)
    target = logger.patch(lambda item: item.update(message="patched"))
    handler = InterceptHandler(target)
    handler.emit(record("shown"))
    logger.disable("thirdparty")
    handler.emit(record("hidden"))
    logger.enable("thirdparty.client")
    handler.emit(record("shown again"))
    assert messages == ["patched", "patched"]


def test_intercepted_exceptions_keep_per_handler_variants(logger: Logger) -> None:
    plain: list[str] = []
    diagnosed: list[str] = []
    logger.add(plain.append, format="{message}")
    logger.add(diagnosed.append, format="{message}", diagnose=True)
    event = record("failed")
    value, divisor = 42, 0
    try:
        value / divisor
    except ZeroDivisionError:
        event.exc_info = sys.exc_info()
        InterceptHandler(logger.patch(lambda item: None)).emit(event)

    assert "ZeroDivisionError: division by zero" in plain[0]
    assert "| divisor" not in plain[0]
    assert "| divisor = 0" in diagnosed[0]
    assert "| value = 42" in diagnosed[0]


def test_empty_exc_info_keeps_standard_logging_text(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message}|{exception}", diagnose=True)
    event = record("outside except")
    event.exc_info = (None, None, None)
    InterceptHandler(logger).emit(event)
    assert messages == ["outside except|NoneType: None\n"]


def test_interception_keeps_registered_level_name(logger: Logger) -> None:
    logger.level("INTERCEPTED_CUSTOM", no=23)
    messages: list[str] = []
    logger.add(messages.append, format="{level}:{level.no}:{message}")
    seen: list[str] = []
    target = logger.patch(lambda item: seen.append(item["level"].name))
    event = record("custom")
    event.levelname = "INTERCEPTED_CUSTOM"
    InterceptHandler(target).emit(event)
    assert messages == ["INTERCEPTED_CUSTOM:23:custom"]
    assert seen == ["INTERCEPTED_CUSTOM"]


def test_unknown_intercepted_level_still_raises(logger: Logger) -> None:
    logger.add(lambda message: None, level="CRITICAL")
    event = record("unknown")
    event.levelname = "NO_SUCH_INTERCEPTED_LEVEL"
    with pytest.raises(ValueError, match="Invalid log level"):
        InterceptHandler(logger).emit(event)


def test_suppressed_interception_does_not_format_message_or_exception(logger: Logger) -> None:
    logger.add(lambda message: None, level="CRITICAL")

    class UnexpectedFormat:
        def __str__(self) -> str:
            raise AssertionError("message formatted")

    class UnexpectedException(Exception):
        calls = 0

        def __str__(self) -> str:
            type(self).calls += 1
            return "exception formatted"

    event = record("%s", UnexpectedFormat())
    try:
        raise UnexpectedException()
    except UnexpectedException:
        event.exc_info = sys.exc_info()
        InterceptHandler(logger).emit(event)

    assert UnexpectedException.calls == 0
