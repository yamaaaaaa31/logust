"""Collection is scoped to sinks eligible for the emitted severity."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from logust import CallerInfo, CollectOptions, Logger, LogLevel, ProcessInfo, ThreadInfo
from logust._logust import PyLogger


def fresh() -> Logger:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.remove()
    return logger


@pytest.mark.parametrize("kind", ["callable", "thread_process", "filter", "raw", "explicit"])
@pytest.mark.parametrize("fast", [True, False])
def test_ineligible_error_sink_does_not_collect_for_info(
    tmp_path: Path, kind: str, fast: bool
) -> None:
    logger = fresh()
    logger._fast_path = fast
    info_path = tmp_path / "info.log"
    logger.add(info_path, level="INFO", format="{message}")
    seen = []
    if kind == "callable":
        logger.add(seen.append, level="ERROR")
    elif kind == "thread_process":
        logger.add(seen.append, level="ERROR", format="{thread.name}|{process.id}|{message}")
    elif kind == "raw":
        logger.add_callback(lambda record: seen.append(record.copy()), level="ERROR")
    else:

        def capture(record):
            seen.append(record.copy())
            return True

        logger.add(
            tmp_path / "error.log",
            level="ERROR",
            format="{message}",
            filter=capture if kind == "filter" else None,
            collect=CollectOptions(caller=True, thread=True, process=True)
            if kind == "explicit"
            else None,
        )
    assert logger._compute_effective_requirements(20) == (False, False, False)
    logger.info("only info")
    logger.complete()
    assert info_path.read_text() == "only info\n"
    assert seen == []
    logger.error("error data")
    logger.complete()
    if kind in ("raw", "filter"):
        assert seen[0]["name"] == __name__
        assert seen[0]["thread"].name
        assert seen[0]["process"].id == os.getpid()
    elif kind == "thread_process":
        assert seen == [f"MainThread|{os.getpid()}|error data"]
    elif kind == "callable":
        assert __name__ in seen[0] and "error data" in seen[0]
    else:
        assert logger._compute_effective_requirements(40) == (True, True, True)
    logger.remove()


def test_custom_threshold_and_bound_family_refresh(tmp_path: Path) -> None:
    logger = fresh()
    logger.level("COLLECTION_MID", no=23)
    logger.add(
        tmp_path / "info.log",
        format="{message}",
        collect=CollectOptions(caller=False, thread=False, process=False),
    )
    bound = logger.bind(user="alice")
    fixed = CallerInfo(name="fixed", function="fixed_fn", line=7, file="fixed.py")
    handler = bound.add(
        tmp_path / "high.log",
        level="COLLECTION_MID",
        format="{name}|{thread.name}|{process.id}|{message}",
        collect=CollectOptions(
            caller=fixed,
            thread=ThreadInfo(name="fixed-thread", id=8),
            process=ProcessInfo(name="fixed-process", id=9),
        ),
    )
    assert logger._compute_effective_requirements(20) == (False, False, False)
    bound.info("low")
    bound.log("COLLECTION_MID", "high")
    bound.complete()
    assert (tmp_path / "high.log").read_text() == "fixed|fixed-thread|9|high\n"
    bound.remove(handler)
    assert logger._compute_effective_requirements(23) == (False, False, False)
    logger.remove()


def test_shared_extra_keeps_json_snapshot_and_override_order(tmp_path: Path) -> None:
    logger = fresh()
    path = tmp_path / "typed.jsonl"
    logger.add(path, serialize=True)
    original = {"values": [1, True, None, {"nested": [2, 3]}]}
    bound = logger.bind(payload=original, tag="bound")
    original["values"].append("changed after bind")
    with logger.contextualize(tag="context", scope="request"):
        bound.info("override", tag="call", event=1)
        bound.info("original")
    bound.info("outside", event=2)
    logger.complete()
    rows = [json.loads(line)["extra"] for line in path.read_text().splitlines()]
    snapshot = {"values": [1, True, None, {"nested": [2, 3]}]}
    assert rows[0] == {"payload": snapshot, "tag": "call", "scope": "request", "event": 1}
    assert rows[1] == {"payload": snapshot, "tag": "bound", "scope": "request"}
    assert rows[2] == {"payload": snapshot, "tag": "bound", "event": 2}
    logger.remove()
