"""``opt(colors=...)`` and ``opt(capture=...)``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger

MARKUP = "<red>alert</red> <b>bold</b>"


@pytest.fixture
def logger() -> Logger:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.remove()
    return logger


class TestColors:
    def test_default_and_true_render_markup(self, logger: Logger) -> None:
        plain: list[str] = []
        colored: list[str] = []
        logger.add(plain.append, format="{message}")
        logger.add(colored.append, format="{message}", colorize=True)

        logger.info(MARKUP)
        logger.opt(colors=True).info(MARKUP)

        assert plain == ["alert bold", "alert bold"]
        assert colored[0] == colored[1] == "\x1b[31malert\x1b[0m \x1b[1mbold\x1b[0m"

    def test_false_keeps_markup_as_text(self, logger: Logger, tmp_path: Path) -> None:
        plain: list[str] = []
        colored: list[str] = []
        filtered: list[str] = []
        log_file = tmp_path / "out.log"
        logger.add(plain.append, format="{message}")
        logger.add(colored.append, format="<green>{message}</green>", colorize=True)
        logger.add(filtered.append, format="{message}", filter=lambda r: True)
        logger.add(str(log_file), format="{message}", colorize=True)

        logger.opt(colors=False).info(MARKUP)
        logger.complete()

        assert plain == [MARKUP]
        assert filtered == [MARKUP]
        assert colored == [f"\x1b[32m{MARKUP}\x1b[0m"]
        assert log_file.read_text(encoding="utf-8") == f"{MARKUP}\n"

    def test_false_on_console(self, logger: Logger, capfd: pytest.CaptureFixture[str]) -> None:
        logger.add(sys.__stderr__, format="{message}", colorize=True)  # type: ignore[arg-type]
        logger.opt(colors=False).info(MARKUP)
        assert capfd.readouterr().err == f"{MARKUP}\n"

    def test_false_only_affects_that_call(self, logger: Logger) -> None:
        out: list[str] = []
        logger.add(out.append, format="{message}")

        logger.opt(colors=False).info(MARKUP)
        logger.info(MARKUP)

        assert out == [MARKUP, "alert bold"]

    def test_false_with_custom_level_and_args(self, logger: Logger) -> None:
        logger.level("COLORS_LVL", no=22)
        out: list[str] = []
        logger.add(out.append, format="{message}")

        logger.opt(colors=False).log("COLORS_LVL", "<red>{}</red>", "x")
        logger.opt(colors=False).warning("<red>{}</red> {user}", 1, user="u")

        assert out == ["<red>x</red>", "<red>1</red> u"]

    def test_false_keeps_bound_context(self, logger: Logger) -> None:
        out: list[str] = []
        logger.add(out.append, format="{message} {extra[user]}")

        logger.bind(user="alice").opt(colors=False).info("<red>x</red>")

        assert out == ["<red>x</red> alice"]

    def test_record_dicts_mark_uncolored_messages(self, logger: Logger) -> None:
        records: list[dict[str, object]] = []
        logger.add_callback(records.append)

        logger.info("a")
        logger.opt(colors=False).info("b")

        assert "colors" not in records[0]
        assert records[1]["colors"] is False
        assert records[1]["message"] == "b"

    def test_serialized_message_is_unchanged(self, logger: Logger) -> None:
        out: list[str] = []
        logger.add(out.append, serialize=True)

        logger.opt(colors=False).info(MARKUP)

        assert json.loads(out[0])["message"] == MARKUP


class TestCapture:
    def test_capture_false_keeps_kwargs_out_of_extra(self, logger: Logger) -> None:
        records: list[dict[str, object]] = []
        logger.add_callback(records.append)

        logger.opt(capture=False).info("{user} did {}", "x", user="bob", other=1)
        logger.info("{user}", user="bob", other=1)

        assert records[0]["message"] == "bob did x"
        assert records[0]["extra"] == {}
        assert records[1]["extra"] == {"other": "1"}

    def test_capture_false_custom_level(self, logger: Logger) -> None:
        logger.level("CAPTURE_LVL", no=21)
        records: list[dict[str, object]] = []
        logger.add_callback(records.append)

        logger.opt(capture=False).log("CAPTURE_LVL", "{a}", a=1)

        assert records[0]["message"] == "1"
        assert records[0]["extra"] == {}

    def test_capture_false_skips_formatting_when_disabled(self, logger: Logger) -> None:
        out: list[str] = []
        logger.add(out.append, level="WARNING", format="{message}")

        class Boom:
            def __format__(self, spec: str) -> str:
                raise AssertionError("formatted")

        logger.opt(capture=False).debug("{x}", x=Boom())

        assert out == []
