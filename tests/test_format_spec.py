"""Python format specs (``{line:05d}``, ``{level: <8}``, ...) in format templates.

File and console sinks render templates in Rust, callable sinks with
``str.format``-style Python code. Both must give what ``format(value, spec)``
gives in Python: Python itself is the oracle here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger

SEP = "\x1f"

STR_FIELDS = (
    "level",
    "level.name",
    "level.icon",
    "message",
    "name",
    "module",
    "function",
    "file",
    "file.name",
    "file.path",
    "thread",
    "thread.name",
    "process",
    "process.name",
    "exception",
    "extra[user]",
    "extra[count]",
    "extra[missing]",
)
INT_FIELDS = ("line", "level.no", "thread.id", "process.id")
# `{elapsed}` changes between records, so it is compared between sinks only
# (test_colorized_specs_match, test_elapsed_spec)
FIELDS = STR_FIELDS + INT_FIELDS

# Specs every supported Python version agrees on. Each is tried on every field:
# where Python accepts it the outputs must match, where Python rejects it
# add() must raise.
SPECS = [
    # fill, align, width
    "<10",
    ">10",
    "^10",
    "^11",
    "*^11",
    "-<12",
    " <8",
    "é>9",
    "<<6",
    "0>8",
    "x<05",
    "<3",
    "1",
    "12",
    # zero padding
    "05",
    "08",
    "<05",
    "0=8",
    "*=8",
    # precision (truncation for str, invalid for int presentation types)
    ".3",
    ">8.2",
    ".0",
    ".50",
    "^7.2s",
    # types
    "s",
    ">10s",
    "d",
    "05d",
    "n",
    "x",
    "X",
    "#x",
    "#010x",
    "o",
    "#o",
    "b",
    "#b",
    "e",
    ".2e",
    "E",
    "#.0e",
    "f",
    ".1f",
    "#.0f",
    "F",
    "g",
    ".3g",
    "#g",
    ".1g",
    "G",
    "%",
    ".1%",
    # sign and alternate form
    "+",
    "-",
    " ",
    "+05",
    " >6",
    "#",
    # grouping
    ",",
    "_",
    ",d",
    "_b",
    "_x",
    "010,",
    "011_x",
    ",.2f",
    "_e",
    "*>+12,",
    # invalid for one kind or for all
    "=5",
    ",s",
    ".2d",
    ",x",
    ",_",
    "abc",
    ".",
    "dd",
]

# Python 3.11 added `z`, 3.14 the fractional-part grouping
if sys.version_info >= (3, 14):
    SPECS += ["z", "zf", "z.2e", ".3,f", ".6_f", ".,", ".,d", "015.5_f"]


def _logger() -> Logger:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.remove()
    return logger


def _oracle_values(message: str) -> dict[str, object]:
    """The record's field values, as Python values (ints for int fields)."""
    logger = _logger()
    out: list[str] = []
    logger.add(out.append, format=SEP.join(f"{{{f}}}" for f in FIELDS), level="TRACE")
    _emit(logger, message)
    values: dict[str, object] = dict(zip(FIELDS, out[0].split(SEP), strict=True))
    for field in INT_FIELDS:
        values[field] = int(str(values[field]))
    return values


def _emit(logger: Logger, message: str) -> None:
    logger.bind(user="alice", count=42).info(message)


def _python_format(value: object, spec: str) -> str | None:
    try:
        return format(value, spec)
    except ValueError:
        return None


def _render_both(tmp_path: Path, fmt: str, message: str, colorize: bool = False) -> tuple[str, str]:
    """(file sink output, callable sink output) of one record."""
    logger = _logger()
    log_file = tmp_path / f"out{len(list(tmp_path.iterdir()))}.log"
    out: list[str] = []
    logger.add(str(log_file), format=fmt, level="TRACE", colorize=colorize)
    logger.add(out.append, format=fmt, level="TRACE", colorize=colorize)
    _emit(logger, message)
    logger.complete()
    logger.remove()
    return log_file.read_text(encoding="utf-8").rstrip("\n"), out[0]


MESSAGES = ["hello", "", "é😀 日本語 message", "a much longer message than any width"]


@pytest.mark.parametrize("message", MESSAGES)
def test_specs_match_python_format(tmp_path: Path, message: str) -> None:
    values = _oracle_values(message)
    for spec in SPECS:
        accepted = [f for f in FIELDS if _python_format(values[f], spec) is not None]
        if not accepted:
            continue
        fmt = SEP.join(f"{{{f}:{spec}}}" for f in accepted)
        expected = SEP.join(str(_python_format(values[f], spec)) for f in accepted)
        file_out, callable_out = _render_both(tmp_path, fmt, message)
        assert file_out == expected, spec
        assert callable_out == expected, spec


def test_specs_python_rejects_raise_at_add(tmp_path: Path) -> None:
    values = _oracle_values("hello")
    checked = 0
    for spec in SPECS:
        for field in FIELDS:
            if field.startswith("extra["):
                continue  # see test_extra_spec_a_string_rejects
            try:
                format(values[field], spec)
            except ValueError as err:
                python_message = str(err)
            else:
                continue
            fmt = f"{{{field}:{spec}}}"
            logger = _logger()
            with pytest.raises(ValueError) as file_err:
                logger.add(str(tmp_path / "x.log"), format=fmt)
            with pytest.raises(ValueError) as callable_err:
                logger.add(lambda _m: None, format=fmt)
            assert str(file_err.value) == str(callable_err.value)
            assert f"(format field '{fmt}')" in str(file_err.value)
            if sys.version_info >= (3, 14):
                assert str(file_err.value).startswith(python_message), fmt
            assert logger._inner.handler_count == 0
            checked += 1
    assert checked > 50


def test_message_d_raises_like_python(tmp_path: Path) -> None:
    logger = _logger()
    with pytest.raises(ValueError, match="Unknown format code 'd' for object of type 'str'"):
        logger.add(str(tmp_path / "x.log"), format="{message:d}")
    with pytest.raises(ValueError, match="Unknown format code 'd' for object of type 'str'"):
        logger.add(lambda _m: None, format="{message:d}")
    with pytest.raises(ValueError, match="Precision not allowed in integer format specifier"):
        logger.add(sys.stderr, format="{line:.2d}")


LOGURU_DEFAULT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


@pytest.mark.parametrize("colorize", [False, True])
@pytest.mark.parametrize(
    "fmt",
    [
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        LOGURU_DEFAULT,
    ],
)
def test_loguru_default_format(tmp_path: Path, fmt: str, colorize: bool) -> None:
    file_out, callable_out = _render_both(tmp_path, fmt, "hi", colorize=colorize)
    assert file_out == callable_out
    # The time may differ by a millisecond between the two sinks' renders: no,
    # both render the same record, so the whole line is identical.
    if not colorize:
        assert " | INFO     | " in file_out
    else:
        assert "\x1b[1;32mINFO    \x1b[0m" in file_out


@pytest.mark.parametrize(
    "fmt",
    [
        "[{level:>8}] [{line:05d}] [{function:^30}] [{message:*<12}] [{thread.name:<12}]",
        "<red>[{message:>10}]</red> {level.no:>3} {elapsed:>14}",
        "<level>{level:^9}|{message:^9}</level>|",
    ],
)
@pytest.mark.parametrize("message", ["hi", "a <red>b</red> c", "<bold>é😀</bold>"])
def test_colorized_specs_match(tmp_path: Path, fmt: str, message: str) -> None:
    file_out, callable_out = _render_both(tmp_path, fmt, message, colorize=True)
    assert file_out == callable_out


def test_colorized_message_markup_takes_no_width(tmp_path: Path) -> None:
    file_out, callable_out = _render_both(tmp_path, "[{message:>6}]", "a<red>b</red>", True)
    assert file_out == callable_out == "[    a\x1b[31mb\x1b[0m]"
    # A precision that cuts the text drops the message's colors
    file_out, callable_out = _render_both(tmp_path, "[{message:>3.1}]", "a<red>b</red>", True)
    assert file_out == callable_out == "[  a]"


def test_level_padding_inside_level_color(tmp_path: Path) -> None:
    """loguru pads ``<level>{level: <8}</level>`` inside the color: ANSI codes
    take no width."""
    file_out, _ = _render_both(tmp_path, "<level>{level: <8}</level>|", "m", colorize=True)
    assert file_out == "\x1b[1;32mINFO    \x1b[0m|"
    file_out, _ = _render_both(tmp_path, "{level:>8}|", "m", colorize=True)
    assert file_out == "\x1b[1;32m    INFO\x1b[0m|"


def test_extra_spec_a_string_rejects(tmp_path: Path) -> None:
    """Extra values render from their text (``str(value)``), in file and
    callable sinks alike: a spec only an int accepts writes the value as is."""
    file_out, callable_out = _render_both(tmp_path, "[{extra[count]:05d}|{extra[user]:+}]", "m")
    assert file_out == callable_out == "[42|alice]"
    # A spec no value accepts is an error
    logger = _logger()
    with pytest.raises(ValueError, match="Invalid format specifier"):
        logger.add(str(tmp_path / "x.log"), format="{extra[count]:abc}")
    with pytest.raises(ValueError, match="Invalid format specifier"):
        logger.add(lambda _m: None, format="{extra[count]:abc}")


def test_elapsed_spec(tmp_path: Path) -> None:
    file_out, callable_out = _render_both(
        tmp_path, "[{elapsed:>14}|{elapsed:.5}|{elapsed:*^16}]", "m"
    )
    assert file_out == callable_out
    assert file_out.startswith("[  00:00:")


def test_empty_spec_and_unknown_fields(tmp_path: Path) -> None:
    file_out, callable_out = _render_both(tmp_path, "{line:}|{nope:>3}|{extra:>3}|{message:}", "m")
    assert file_out == callable_out
    assert file_out.endswith("|{nope:>3}|{extra:>3}|m")


def test_serialized_sink_ignores_template_specs(tmp_path: Path) -> None:
    logger = _logger()
    logger.add(str(tmp_path / "x.json"), format="{message:d}", serialize=True)
