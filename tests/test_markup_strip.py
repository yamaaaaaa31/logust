"""Color markup is stripped from non-colorized output."""

from __future__ import annotations

from pathlib import Path

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger


@pytest.fixture
def logger() -> Logger:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.disable()
    return logger


def test_callable_sink_strips_markup(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message}")

    logger.info("<green>hello</green> <bold>world</bold> <nope>x</nope>")

    assert messages == ["hello world <nope>x</nope>"]


def test_callable_sink_with_filter_strips_markup(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message}", filter=lambda _: True)

    logger.info("<red>hello</red>")

    assert messages == ["hello"]


def test_file_sink_strips_markup(logger: Logger, tmp_path: Path) -> None:
    log_file = tmp_path / "test.log"
    logger.add(str(log_file), format="{message}")

    logger.info("<green>hello</green>")
    logger.complete()

    assert log_file.read_text() == "hello\n"


FORMAT_MARKUP = "<green>{level}</green> <level>{message}</level> <nope>x</nope>"


def test_callable_sink_strips_format_markup(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format=FORMAT_MARKUP)

    logger.info("<red>m</red>")

    assert messages == ["INFO m <nope>x</nope>"]


def test_file_sink_strips_format_markup(logger: Logger, tmp_path: Path) -> None:
    log_file = tmp_path / "test.log"
    logger.add(str(log_file), format=FORMAT_MARKUP)

    logger.info("<red>m</red>")
    logger.complete()

    assert log_file.read_text() == "INFO m <nope>x</nope>\n"


def test_level_width_spec_is_not_read_as_markup(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="<level>{level:<8}</level>|")

    logger.info("x")

    assert messages == ["INFO    |"]
