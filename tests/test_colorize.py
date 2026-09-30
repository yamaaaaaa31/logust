"""``colorize`` for callable, stream, and file sinks."""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger

GREEN_INFO = "\x1b[1;32mINFO\x1b[0m"


class TtyStream(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture
def logger() -> Logger:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.disable()
    return logger


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("NO_COLOR", "FORCE_COLOR", "CI", "GITHUB_ACTIONS", "PYCHARM_HOSTED", "TERM"):
        monkeypatch.delenv(var, raising=False)


def test_callable_sink_colorize(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{level} {function} {message}", colorize=True)

    logger.info("<green>hi</green> <nope>x</nope>")

    assert messages == [
        f"{GREEN_INFO} \x1b[36mtest_callable_sink_colorize\x1b[0m \x1b[32mhi\x1b[0m <nope>x</nope>"
    ]


def test_callable_sink_colorize_pads_inside_color(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{level:<8}|", colorize=True)

    logger.info("x")

    assert messages == ["\x1b[1;32mINFO    \x1b[0m|"]


def test_callable_sink_colorize_custom_level(logger: Logger) -> None:
    messages: list[str] = []
    logger.level("NOTICE", no=26, color="cyan")
    logger.add(messages.append, format="{level}", colorize=True)

    logger.log("NOTICE", "x")

    assert messages == ["\x1b[1;36mNOTICE\x1b[0m"]


def test_callable_sink_default_has_no_color(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{level} {message}")

    logger.info("<green>hi</green>")

    assert messages == ["INFO hi"]


def test_stream_sink_autodetects_tty(logger: Logger) -> None:
    plain = io.StringIO()
    tty = TtyStream()
    logger.add(plain, format="{level}")
    logger.add(tty, format="{level}")

    logger.info("x")

    assert plain.getvalue() == "INFO\n"
    assert tty.getvalue() == f"{GREEN_INFO}\n"


def test_stream_sink_serialize_has_no_color(logger: Logger) -> None:
    tty = TtyStream()
    logger.add(tty, serialize=True)

    logger.info("x")

    assert "\x1b[" not in tty.getvalue()


def test_force_color_applies_to_standard_stream(
    logger: Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        logger.add(sys.stdout, format="{level}")
        logger.info("x")

    assert buf.getvalue() == f"{GREEN_INFO}\n"


def test_no_color_applies_to_standard_stream(
    logger: Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("FORCE_COLOR", "1")
    tty = TtyStream()
    with contextlib.redirect_stdout(tty):
        logger.add(sys.stdout, format="{level}")
        logger.info("x")

    assert tty.getvalue() == "INFO\n"


def test_force_color_ignored_for_other_streams(
    logger: Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    stream = io.StringIO()
    logger.add(stream, format="{level}")

    logger.info("x")

    assert stream.getvalue() == "INFO\n"


def test_should_colorize_ci_and_dumb_term(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM", "dumb")
    assert Logger._should_colorize(TtyStream()) is True
    if sys.__stdout__ is not None:
        assert Logger._should_colorize(sys.__stdout__) is False
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        assert Logger._should_colorize(sys.__stdout__) is True


def test_file_sink_colorize(logger: Logger, tmp_path: Path) -> None:
    colored = tmp_path / "colored.log"
    plain = tmp_path / "plain.log"
    logger.add(str(colored), format="{level} {message}", colorize=True)
    logger.add(str(plain), format="{level} {message}")

    logger.info("<green>hi</green>")
    logger.complete()

    assert colored.read_text() == f"{GREEN_INFO} \x1b[32mhi\x1b[0m\n"
    assert plain.read_text() == "INFO hi\n"


FORMAT_MARKUP = "<green>{level}</green>|<level>{message}</level>|{level}"
# <green> replaces the default level style; <level> survives the reset after </red>
COLORED_MARKUP = (
    "\x1b[32mWARNING\x1b[0m|\x1b[1;33m\x1b[31mr\x1b[0m\x1b[1;33m t\x1b[0m|\x1b[1;33mWARNING\x1b[0m"
)


def test_callable_sink_colorizes_format_markup(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format=FORMAT_MARKUP, colorize=True)

    logger.warning("<red>r</red> t")

    assert messages == [COLORED_MARKUP]


def test_file_sink_colorizes_format_markup(logger: Logger, tmp_path: Path) -> None:
    log_file = tmp_path / "colored.log"
    logger.add(str(log_file), format=FORMAT_MARKUP, colorize=True)

    logger.warning("<red>r</red> t")
    logger.complete()

    assert log_file.read_text() == f"{COLORED_MARKUP}\n"


def test_level_markup_without_level_token(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="<level>{message}</level>", colorize=True)

    logger.error("x")

    assert messages == ["\x1b[1;31mx\x1b[0m"]
