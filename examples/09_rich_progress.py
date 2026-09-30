#!/usr/bin/env python3

"""Logging above a rich progress bar with Logust.

Logust's default console handler writes straight to the process stdout, which
corrupts a live rich display. Replace it with a callable sink that prints through
the progress console, so rich erases the bar, prints the log line, and redraws.

Requirements:
    pip install rich

Run:
    python examples/09_rich_progress.py
"""

import random
import time

from rich.progress import Progress
from rich.text import Text

from logust import logger

logger.remove()

with Progress() as progress:
    handler_id = logger.add(
        lambda msg: progress.console.print(Text.from_ansi(msg)),
        format="{time} | {level:<8} | {message}",
        colorize=True,
    )

    task = progress.add_task("Processing", total=20)

    for i in range(20):
        time.sleep(0.15)

        if i % 5 == 0:
            logger.info(f"Checkpoint <green>{i}</green> reached")

        if random.random() < 0.1:
            logger.warning(f"Item <yellow>{i}</yellow> needed a retry")

        progress.advance(task)

    logger.success("<bold>All items processed</bold>")
    logger.remove(handler_id)
