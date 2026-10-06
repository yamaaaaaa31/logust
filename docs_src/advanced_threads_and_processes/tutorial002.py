import multiprocessing
from pathlib import Path

from logust import logger


def setup_logging():
    logger.remove()
    logger.add("workers.log", format="{process.name} | {message}", enqueue=True)


def work(task_id):
    setup_logging()
    for step in range(500):
        logger.info("Task {} step {}", task_id, step)
    logger.complete()


if __name__ == "__main__":
    Path("workers.log").unlink(missing_ok=True)
    setup_logging()

    ctx = multiprocessing.get_context("spawn")
    processes = [ctx.Process(target=work, args=(n,), name=f"Worker-{n}") for n in range(3)]
    for process in processes:
        process.start()
    for process in processes:
        process.join()

    logger.info("All workers finished")
    logger.complete()

    with open("workers.log") as f:
        lines = f.read().splitlines()
    print(len(lines), "lines")
    print(lines[0])
    print(lines[-1])
