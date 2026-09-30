"""Log lines cooperate with a live rich progress bar."""

from __future__ import annotations

import io
import sys
from collections.abc import Callable

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger

pytest.importorskip("rich")

from rich.console import Console  # noqa: E402
from rich.progress import Progress  # noqa: E402
from rich.text import Text  # noqa: E402

ERASE_LINE = "\r\x1b[2K"


@pytest.fixture
def logger() -> Logger:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.disable()
    return logger


def run_progress(logger: Logger, add_sink: Callable[[Progress], None]) -> str:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=True, width=60, color_system="standard")
    with Progress(console=console, auto_refresh=False) as progress:
        task = progress.add_task("work", total=3)
        add_sink(progress)
        for i in range(3):
            progress.advance(task)
            progress.refresh()
            logger.info(f"<green>step {i}</green>")

    return buffer.getvalue()


def test_callable_sink_prints_above_progress_bar(logger: Logger) -> None:
    output = run_progress(
        logger,
        lambda progress: logger.add(
            lambda msg: progress.console.print(Text.from_ansi(msg)),
            format="{level} {message}",
            colorize=True,
        ),
    )

    for i in range(3):
        assert f"{ERASE_LINE}\x1b[1;32mINFO\x1b[0m \x1b[32mstep {i}\x1b[0m\nwork " in output


def test_stream_sink_bound_to_rich_stdout_proxy(logger: Logger) -> None:
    output = run_progress(
        logger,
        lambda _: logger.add(sys.stdout, format="{level} {message}", colorize=True),
    )

    for i in range(3):
        assert f"{ERASE_LINE}\x1b[1;32mINFO\x1b[0m \x1b[32mstep {i}\x1b[0m\nwork " in output
