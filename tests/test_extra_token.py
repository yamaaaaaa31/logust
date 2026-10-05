"""``{extra}`` renders the whole extra dict like loguru (``str(dict)``)."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import Any

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger
from logust._template import ParsedCallableTemplate

FMT = "{message} {extra}"


def _logger() -> Logger:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.remove()
    return logger


def _emit(logger: Logger, extra: dict[str, Any], level: str = "info") -> None:
    bound = logger.bind(**extra) if extra else logger
    if level == "info":
        bound.info("msg")
    else:
        bound.log(level, "msg")


def _render_file(tmp_path: Path, extra: dict[str, Any], fmt: str = FMT) -> str:
    logger = _logger()
    log_file = tmp_path / "out.log"
    logger.add(str(log_file), format=fmt)
    _emit(logger, extra)
    logger.complete()
    return log_file.read_text(encoding="utf-8").rstrip("\n")


def _render_callable(extra: dict[str, Any], fmt: str = FMT, **add: Any) -> str:
    logger = _logger()
    out: list[str] = []
    logger.add(out.append, format=fmt, **add)
    _emit(logger, extra)
    assert len(out) == 1
    return out[0]


EXTRAS: list[dict[str, Any]] = [
    {},
    {"user": "alice"},
    {"n": 1, "ratio": 1.5, "ok": True, "missing": None},
    {"b": 2, "a": 1},
    {"items": [1, "a"], "mapping": {"k": "v"}},
    {"quote": "it's", "both": "'\"", "newline": "a\nb", "tab": "\t", "backslash": "a\\b"},
    {"ctrl": "\x00\x1f\x7f", "nbsp": "\xa0", "unicode": "日本語 é"},
]


@pytest.mark.parametrize("extra", EXTRAS)
def test_matches_python_str_of_sorted_dict(tmp_path: Path, extra: dict[str, Any]) -> None:
    expected = f"msg {dict(sorted(extra.items()))}"
    assert _render_file(tmp_path, extra) == expected
    assert _render_callable(extra) == expected


@pytest.mark.parametrize("extra", EXTRAS)
def test_sink_parity(tmp_path: Path, extra: dict[str, Any]) -> None:
    file_out = _render_file(tmp_path, extra)
    assert _render_callable(extra) == file_out
    assert _render_callable(extra, filter=lambda r: True) == file_out
    assert _render_callable(extra, colorize=True) == file_out


def test_console_parity(capfd: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    extra = {"user": "bob", "n": 3}
    logger = _logger()
    logger.add(sys.__stderr__, format=FMT, colorize=False)  # type: ignore[arg-type]
    _emit(logger, extra)
    err = capfd.readouterr().err
    assert err.rstrip("\n") == _render_file(tmp_path, extra)


def test_custom_level_parity(tmp_path: Path) -> None:
    logger = _logger()
    logger.level("EXTRA_LVL", no=23)
    log_file = tmp_path / "custom.log"
    out: list[str] = []
    filtered: list[str] = []
    logger.add(str(log_file), format=FMT)
    logger.add(out.append, format=FMT)
    logger.add(filtered.append, format=FMT, filter=lambda r: True)
    _emit(logger, {"k": "v", "n": 2}, level="EXTRA_LVL")
    logger.complete()
    expected = "msg {'k': 'v', 'n': 2}"
    assert log_file.read_text(encoding="utf-8").rstrip("\n") == expected
    assert out == [expected]
    assert filtered == [expected]


def test_per_call_kwargs_are_included(tmp_path: Path) -> None:
    logger = _logger()
    out: list[str] = []
    logger.add(out.append, format=FMT)
    logger.bind(a=1).info("msg", b="x")
    assert out == ["msg {'a': 1, 'b': 'x'}"]


def test_other_types_use_str() -> None:
    when = datetime.datetime(2024, 1, 2, 3, 4, 5)
    assert _render_callable({"when": when}) == f"msg {{'when': {when}}}"


def test_extra_with_spec_is_literal(tmp_path: Path) -> None:
    fmt = "{message} {extra:>5}"
    assert _render_file(tmp_path, {"a": 1}, fmt) == "msg {extra:>5}"
    assert _render_callable({"a": 1}, fmt) == "msg {extra:>5}"


def test_extra_key_and_whole_dict_together(tmp_path: Path) -> None:
    fmt = "{extra[a]} {extra}"
    assert _render_file(tmp_path, {"a": 1}, fmt) == "1 {'a': 1}"
    assert _render_callable({"a": 1}, fmt) == "1 {'a': 1}"


def test_template_falls_back_without_extra_repr() -> None:
    template = ParsedCallableTemplate(FMT)
    assert template.needs_extra_repr
    assert template.format({"message": "m", "extra": {"b": 2, "a": "x"}}) == "m {'a': 'x', 'b': 2}"
    assert template.format({"message": "m"}) == "m {}"


def test_requirements_flag() -> None:
    assert ParsedCallableTemplate("{extra}").lightweight_requirements_for_rust()[12] is True
    assert ParsedCallableTemplate("{extra[a]}").lightweight_requirements_for_rust()[12] is False
