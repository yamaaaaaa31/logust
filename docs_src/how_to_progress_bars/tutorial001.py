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

    task = progress.add_task("Processing", total=100)
    for i in range(100):
        time.sleep(0.01)
        if i % 25 == 0:
            logger.info(f"Checkpoint <green>{i}</green> reached")
        progress.advance(task)

    logger.remove(handler_id)
