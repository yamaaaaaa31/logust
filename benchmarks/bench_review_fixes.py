"""Bounded release-wheel benchmark for collection, context and callback changes.

Run outside the checkout with a wheel-installed interpreter, for example:
    cd /tmp
    /path/to/venv/bin/python /path/to/bench_review_fixes.py --calls 30000

Compare alternating invocations of baseline and candidate on the same machine.
All file/callback cases validate their output; the timer includes flush completion.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

import logust
from logust import Logger, LogLevel
from logust._logust import PyLogger


def run(calls: int) -> dict:
    if Path(sys.prefix) not in Path(logust.__file__).parents:
        raise RuntimeError(f"Expected an installed wheel, imported {logust.__file__}")
    results = {}
    with tempfile.TemporaryDirectory(prefix="logust-bench-") as directory:
        for kind in (
            "file_message",
            "file_default",
            "file_json",
            "callable_message",
            "console_message",
            "error_callable",
            "error_filter",
            "bound_empty_extra",
            "bound_large",
            "bound_large_extra",
            "filtered_error",
            "filtered_exception",
            "filtered_opt_exception",
        ):
            logger = Logger(PyLogger(LogLevel.Trace))
            logger.remove()
            output = Path(directory) / (kind + ".log")
            seen = []
            console_backup = None
            if kind == "callable_message":
                logger.add(seen.append, format="{message}")
            elif kind == "console_message":
                console_backup = os.dup(2)
                with open(os.devnull, "w") as null:
                    os.dup2(null.fileno(), 2)
                logger.add(sys.__stderr__, format="{message}", colorize=False)
            elif kind.startswith("filtered_"):
                logger.add(seen.append, level="CRITICAL", format="{message}")
            else:
                options = {}
                if kind == "file_json":
                    options["serialize"] = True
                elif kind != "file_default":
                    options["format"] = "{message}"
                logger.add(output, **options)
            if kind == "error_callable":
                logger.add(seen.append, level="ERROR")
            elif kind == "error_filter":
                logger.add(
                    Path(directory) / "errors.log",
                    level="ERROR",
                    format="{message}",
                    filter=lambda record, seen=seen: seen.append(record) or True,
                )
            if kind in ("bound_large", "bound_large_extra"):
                logger = logger.bind(payload=list(range(10000)))
            elif kind == "bound_empty_extra":
                logger = logger.bind(payload=[])
            if kind in ("bound_large_extra", "bound_empty_extra"):

                def emit(logger=logger):
                    logger.info("payload", event=1)
            elif kind == "filtered_exception":

                def emit(logger=logger):
                    logger.exception("payload")
            elif kind == "filtered_opt_exception":
                configured = logger.opt(exception=True)

                def emit(configured=configured):
                    configured.error("payload")
            elif kind == "filtered_error":

                def emit(logger=logger):
                    logger.error("payload")
            else:

                def emit(logger=logger):
                    logger.info("payload")

            count = (
                min(calls, 3000)
                if kind in ("bound_large_extra", "filtered_exception", "filtered_opt_exception")
                else calls
            )
            try:
                raise ValueError("benchmark exception")
            except ValueError:
                for _ in range(100):
                    emit()
                logger.complete()
                gc.disable()
                try:
                    started = time.perf_counter_ns()
                    for _ in range(count):
                        emit()
                    logger.complete()
                    elapsed = time.perf_counter_ns() - started
                finally:
                    gc.enable()
            logger.remove()
            if console_backup is not None:
                os.dup2(console_backup, 2)
                os.close(console_backup)
            fingerprint = None
            if output.exists():
                lines = output.read_text().splitlines()
                assert len(lines) == count + 100, (kind, len(lines), count)
                if kind == "file_json":
                    rows = [json.loads(line) for line in lines]
                    assert all(
                        row["message"] == "payload" and row["level"] == "INFO" for row in rows
                    )
                    normalized = [
                        {
                            key: row[key]
                            for key in ("level", "message", "name", "function", "line", "extra")
                            if key in row
                        }
                        for row in rows
                    ]
                elif kind == "file_default":
                    assert all(line.endswith(" - payload") for line in lines)
                    normalized = [line.split(" | ", 1)[1] for line in lines]
                else:
                    assert lines == ["payload"] * (count + 100)
                    normalized = lines
                fingerprint = hashlib.sha256(
                    json.dumps(normalized, sort_keys=True).encode()
                ).hexdigest()
            elif kind == "callable_message":
                assert seen == ["payload"] * (count + 100)
                fingerprint = hashlib.sha256(json.dumps(seen).encode()).hexdigest()
            else:
                assert seen == []
            if kind in ("error_callable", "error_filter"):
                assert seen == [], "Ineligible ERROR sink was invoked"
            results[kind] = {
                "ns_per_call": elapsed / count,
                "calls": count,
                "fingerprint": fingerprint,
            }
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "package": logust.__file__,
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calls", type=int, default=30000)
    args = parser.parse_args()
    if args.calls < 1:
        parser.error("--calls must be positive")
    print(json.dumps(run(args.calls), sort_keys=True))
