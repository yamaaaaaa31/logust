"""Time-based rotation across a daylight saving time change.

``TZ`` is process-wide and chrono re-reads it at most once per second, so the
test switches the zone for the whole process, waits for the Rust core to pick
it up, and restores it afterwards. chrono ignores ``TZ`` on Windows.
"""

from __future__ import annotations

import datetime
import os
import sys
import time
from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from logust import Logger, LogLevel

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="chrono ignores TZ on Windows")

# chrono checks TZ again once its per-thread cache is older than one second.
TZ_REFRESH_SECONDS = 1.1


def _dst_gap_rule(start: datetime.datetime) -> str:
    """POSIX TZ rule whose standard time is UTC and whose DST starts at ``start``.

    The clock jumps forward by one hour (padded by the seconds needed for the
    gap to end on a whole minute, like every real transition does) and falls
    back 40 days later; the end has to be in another month for chrono.
    """
    shift = "1" if start.second == 0 else f"1:00:{60 - start.second:02d}"
    end = start + datetime.timedelta(days=40)
    start_day = start.timetuple().tm_yday - 1
    end_day = end.timetuple().tm_yday - 1
    return f"LST0LDT-{shift},{start_day}/{start:%H:%M:%S},{end_day}/{end:%H:%M:%S}"


@pytest.fixture
def process_tz() -> Generator[Callable[[str], None], None, None]:
    """Set ``TZ`` for the process until the test ends, then restore it."""
    previous = os.environ.get("TZ")

    def apply(rule: str) -> None:
        os.environ["TZ"] = rule
        time.sleep(TZ_REFRESH_SECONDS)

    yield apply

    if previous is None:
        del os.environ["TZ"]
    else:
        os.environ["TZ"] = previous
    # The next local-time lookup after this re-reads the real zone.
    time.sleep(TZ_REFRESH_SECONDS)


def _rotated_files(directory: Path, log_file: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.suffix == ".log" and p != log_file)


def test_hourly_rotation_survives_a_dst_gap(
    session_logger: Logger, tmp_path: Path, process_tz: Callable[[str], None]
) -> None:
    # DST starts a few seconds after the sink is opened, so the next top of
    # the hour is a wall-clock time that never happens.
    now = datetime.datetime.now(datetime.timezone.utc)
    transition = (now + datetime.timedelta(seconds=4)).replace(microsecond=0)
    process_tz(_dst_gap_rule(transition))

    log_file = tmp_path / "app.log"
    handler_id = session_logger.add(
        log_file, level=LogLevel.Trace, format="{message}", rotation="hourly"
    )
    try:
        session_logger.info("before")
        session_logger.complete()
        assert not _rotated_files(tmp_path, log_file)

        deadline = time.monotonic() + 15
        while not _rotated_files(tmp_path, log_file):
            assert time.monotonic() < deadline, "no rotation across the DST gap"
            time.sleep(0.1)
            session_logger.info("after")
            session_logger.complete()
    finally:
        session_logger.remove(handler_id)

    (rotated,) = _rotated_files(tmp_path, log_file)
    assert "before" in rotated.read_text()
    assert "before" not in log_file.read_text()
    assert "after" in log_file.read_text()
