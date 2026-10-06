"""File sinks must not lose logged lines.

* A synchronous file sink writes each line to the file before the logging call
  returns, so it is visible to ``tail -f`` and survives SIGTERM, ``os._exit()``
  or a crash without ``complete()``.
* An ``enqueue=True`` sink reaches the file within ~100 ms, even under a steady
  trickle of messages, and is drained at normal exit.
* Normal-exit flushing does not depend on the logger being freed during
  interpreter teardown, so filters and callable sinks that refer back to the
  logger (a reference cycle) do not lose lines.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from logust import Logger


def _run(code: str, log_file: Path) -> subprocess.CompletedProcess[str]:
    script = "from logust import logger\nlogger.remove()\n" + textwrap.dedent(code)
    return subprocess.run(
        [sys.executable, "-c", script, str(log_file)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


class TestSyncSinkWritesThrough:
    @pytest.mark.parametrize(
        "options",
        [{}, {"rotation": "10 MB"}, {"filter": lambda r: True}],
        ids=["plain", "rotation", "filter"],
    )
    def test_line_is_in_file_without_complete(
        self, session_logger: Logger, tmp_path: Path, options: dict[str, object]
    ) -> None:
        log_file = tmp_path / "app.log"
        handler_id = session_logger.add(log_file, format="{message}", **options)  # type: ignore[arg-type]
        try:
            session_logger.info("first")
            assert _read(log_file) == "first\n"
            session_logger.info("second")
            assert _read(log_file) == "first\nsecond\n"
        finally:
            session_logger.remove(handler_id)

    def test_os_exit_keeps_lines(self, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        result = _run(
            """
            import os, sys
            logger.add(sys.argv[1], format="{message}")
            logger.info("before exit")
            os._exit(0)
            """,
            log_file,
        )
        assert result.returncode == 0, result.stderr
        assert _read(log_file) == "before exit\n"

    @pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM is not a signal on Windows")
    def test_sigterm_keeps_lines(self, tmp_path: Path) -> None:
        # Uvicorn re-raises SIGTERM after a graceful shutdown; the default
        # action kills the process without running atexit handlers.
        log_file = tmp_path / "app.log"
        result = _run(
            """
            import os, signal, sys
            logger.add(sys.argv[1], format="{message}")
            logger.info("shutting down")
            os.kill(os.getpid(), signal.SIGTERM)
            """,
            log_file,
        )
        assert result.returncode == -15, result.stderr
        assert _read(log_file) == "shutting down\n"


class TestNormalExitFlush:
    """Lines reach the file at normal exit without ``complete()``."""

    @pytest.mark.parametrize("enqueue", [False, True], ids=["sync", "enqueue"])
    @pytest.mark.parametrize(
        "setup",
        [
            'logger.add(sys.argv[1], format="{message}", enqueue=ENQUEUE)',
            'logger.add(sys.argv[1], format="{message}", enqueue=ENQUEUE, filter=lambda r: True)',
            'logger.add(sys.argv[1], format="{message}", enqueue=ENQUEUE)\n'
            "logger.add(lambda m: None)",
            # A logger kept alive by a reference cycle through a filter closure.
            "def keep(record):\n"
            "    return logger is not None\n"
            'logger.add(sys.argv[1], format="{message}", enqueue=ENQUEUE, filter=keep)',
        ],
        ids=["plain", "lambda-filter", "callable-sink", "closure-filter"],
    )
    def test_lines_written_at_exit(self, tmp_path: Path, setup: str, enqueue: bool) -> None:
        log_file = tmp_path / "app.log"
        code = "import sys\nENQUEUE = " + repr(enqueue) + "\n" + setup + "\n"
        code += "for i in range(3):\n    logger.info('line {}', i)\n"
        result = _run(code, log_file)
        assert result.returncode == 0, result.stderr
        assert _read(log_file) == "line 0\nline 1\nline 2\n"

    def test_enqueue_drained_after_user_atexit_handlers(self, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        result = _run(
            """
            import atexit, sys
            logger.add(sys.argv[1], format="{message}", enqueue=True, filter=lambda r: True)
            atexit.register(lambda: logger.info("from atexit"))
            for i in range(1000):
                logger.info("line {}", i)
            """,
            log_file,
        )
        assert result.returncode == 0, result.stderr
        lines = _read(log_file).splitlines()
        assert len(lines) == 1001
        assert lines[-1] == "from atexit"


class TestEnqueueFlushInterval:
    def test_steady_trickle_is_flushed(self, session_logger: Logger, tmp_path: Path) -> None:
        # A message every 20 ms never lets the writer go idle for 100 ms; the
        # first line must still reach the file without waiting for the buffer
        # to fill or for complete().
        log_file = tmp_path / "app.log"
        handler_id = session_logger.add(log_file, format="{message}", enqueue=True)
        try:
            session_logger.info("first")
            deadline = time.monotonic() + 5
            while "first" not in _read(log_file):
                assert time.monotonic() < deadline, "enqueue sink never flushed"
                session_logger.info("tick")
                time.sleep(0.02)
        finally:
            session_logger.remove(handler_id)
