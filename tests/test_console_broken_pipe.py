"""Console sinks on a closed pipe (``python app.py | head -1``).

Each test starts a child process whose stdout (or stderr) is a pipe, reads the
first line, closes the read end, then tells the child over stdin to keep
logging. From then on every console write fails with ``EPIPE`` (Python ignores
``SIGPIPE``), and the error must follow the sink's ``catch`` policy instead of
escaping the logging call as ``pyo3_runtime.PanicException``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

# Each child logs one line, waits for the parent, then logs onto the closed pipe.
CHILD_TEMPLATE = """
import sys
from logust import Logger, LogLevel
from logust._logust import PyLogger

logger = Logger(PyLogger(LogLevel.Trace))
logger.disable()
logger.add({sink}, format="{{message}}", catch={catch})
logger.info("first")
sys.stdin.readline()
try:
    logger.info("second")
    logger.info("third")
except BaseException as exc:  # noqa: BLE001 - PanicException is a BaseException
    print(f"raised {{type(exc).__name__}}: {{exc}}", file={marker_stream})
print("survived", file={marker_stream})
"""

DEFAULT_HANDLER_CHILD = """
import sys
from logust import logger

logger.info("first")
sys.stdin.readline()
logger.info("second")
print("survived", file=sys.stderr)
"""

STREAM_WRAPPER_CHILD = """
import os
import sys
from logust import Logger, LogLevel
from logust._logust import PyLogger


class RawStdout:
    # Unbuffered so nothing is left for the interpreter to flush (and fail) at exit.
    def write(self, text):
        os.write(1, text.encode())

    def flush(self):
        pass


logger = Logger(PyLogger(LogLevel.Trace))
logger.disable()
# A replaced sys.stdout goes through the Python stream writer, not the Rust console sink.
sys.stdout = RawStdout()
logger.add(sys.stdout, format="{{message}}", catch={catch})
logger.info("first")
sys.stdin.readline()
try:
    logger.info("second")
except BaseException as exc:  # noqa: BLE001
    print(f"raised {{type(exc).__name__}}", file=sys.stderr)
print("survived", file=sys.stderr)
"""


def run_child(code: str, *, close: str) -> tuple[str, str, int]:
    """Run ``code`` in a child, close its ``close`` pipe after one line, let it go on.

    Returns the text read from the other pipe, the first line read from the
    closed pipe, and the exit code.
    """
    proc = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(code)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    closed_pipe, kept_pipe = (
        (proc.stdout, proc.stderr) if close == "stdout" else (proc.stderr, proc.stdout)
    )
    first = closed_pipe.readline()
    closed_pipe.close()
    proc.stdin.write("go\n")
    proc.stdin.close()
    kept = kept_pipe.read()
    kept_pipe.close()
    code_ = proc.wait(timeout=60)
    return kept, first, code_


def console_child(sink: str, catch: str, marker_stream: str) -> str:
    return CHILD_TEMPLATE.format(sink=sink, catch=catch, marker_stream=marker_stream)


def assert_broken_pipe(line: str) -> None:
    if sys.platform == "win32":
        # A closed pipe surfaces as ERROR_NO_DATA / ERROR_BROKEN_PIPE; both are
        # OSError subclasses but the exact class is not pinned down here.
        assert "raised " in line and "Error" in line
    else:
        assert line.startswith("raised BrokenPipeError:")


class TestStdoutSink:
    def test_catch_none_is_silent(self) -> None:
        stderr, first, code = run_child(
            console_child("sys.__stdout__", "None", "sys.stderr"), close="stdout"
        )
        assert first == "first\n"
        assert code == 0
        assert stderr == "survived\n"

    def test_catch_true_reports_once_per_failed_record(self) -> None:
        stderr, first, code = run_child(
            console_child("sys.__stdout__", "True", "sys.stderr"), close="stdout"
        )
        assert first == "first\n"
        assert code == 0
        assert stderr.count("--- Logging error in Logust Handler #") == 2
        assert stderr.count("--- End of logging error ---") == 2
        assert "Record was: INFO | second" in stderr
        assert "Record was: INFO | third" in stderr
        assert "OSError: " in stderr
        assert "PanicException" not in stderr
        assert stderr.endswith("survived\n")

    def test_catch_false_raises_broken_pipe_error(self) -> None:
        stderr, first, code = run_child(
            console_child("sys.__stdout__", "False", "sys.stderr"), close="stdout"
        )
        assert first == "first\n"
        assert code == 0
        lines = stderr.splitlines()
        assert len(lines) == 2, stderr
        assert_broken_pipe(lines[0])
        assert "PanicException" not in lines[0]
        assert lines[1] == "survived"


class TestStderrSink:
    def test_catch_none_is_silent(self) -> None:
        stdout, first, code = run_child(
            console_child("sys.__stderr__", "None", "sys.stdout"), close="stderr"
        )
        assert first == "first\n"
        assert code == 0
        assert stdout == "survived\n"

    def test_catch_true_cannot_report_on_broken_stderr_and_continues(self) -> None:
        # The report itself targets stderr, which is the broken pipe: it is
        # dropped instead of raising or looping.
        stdout, first, code = run_child(
            console_child("sys.__stderr__", "True", "sys.stdout"), close="stderr"
        )
        assert first == "first\n"
        assert code == 0
        assert stdout == "survived\n"

    def test_catch_false_raises_broken_pipe_error(self) -> None:
        stdout, first, code = run_child(
            console_child("sys.__stderr__", "False", "sys.stdout"), close="stderr"
        )
        assert first == "first\n"
        assert code == 0
        lines = stdout.splitlines()
        assert len(lines) == 2, stdout
        assert_broken_pipe(lines[0])
        assert lines[1] == "survived"


def test_default_console_handler_survives_closed_stdout() -> None:
    stderr, first, code = run_child(DEFAULT_HANDLER_CHILD, close="stdout")
    assert first.endswith("first\n")
    assert code == 0
    assert stderr == "survived\n"


class TestPythonStreamWrapper:
    """``logger.add(sys.stdout)`` with a replaced ``sys.stdout`` uses the Python writer."""

    def test_catch_none_is_silent(self) -> None:
        stderr, first, code = run_child(STREAM_WRAPPER_CHILD.format(catch="None"), close="stdout")
        assert first == "first\n"
        assert code == 0
        assert stderr == "survived\n"

    def test_catch_true_reports(self) -> None:
        stderr, first, code = run_child(STREAM_WRAPPER_CHILD.format(catch="True"), close="stdout")
        assert first == "first\n"
        assert code == 0
        assert stderr.count("--- Logging error in Logust Handler #") == 1
        # Windows reports a closed pipe as OSError(EINVAL) from Python file writes
        assert ("OSError" if sys.platform == "win32" else "BrokenPipeError") in stderr
        assert stderr.endswith("survived\n")

    def test_catch_false_raises(self) -> None:
        stderr, first, code = run_child(STREAM_WRAPPER_CHILD.format(catch="False"), close="stdout")
        assert first == "first\n"
        assert code == 0
        raised, survived = stderr.splitlines()
        # Windows reports a closed pipe as OSError(EINVAL) from Python file writes
        assert raised == ("raised OSError" if sys.platform == "win32" else "raised BrokenPipeError")
        assert survived == "survived"


@pytest.mark.skipif(sys.platform == "win32", reason="SIGPIPE does not exist on Windows")
def test_sigpipe_disposition_is_untouched() -> None:
    # Python ignores SIGPIPE so that writes get EPIPE; logust must leave it that way.
    child = """
    import signal, sys
    from logust import Logger, LogLevel
    from logust._logust import PyLogger
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.disable()
    logger.add(sys.__stdout__, format="{message}")
    logger.info("first")
    sys.stdin.readline()
    logger.info("second")
    print("survived", signal.getsignal(signal.SIGPIPE) is signal.SIG_IGN, file=sys.stderr)
    """
    stderr, first, code = run_child(child, close="stdout")
    assert first == "first\n"
    assert code == 0
    assert stderr == "survived True\n"
