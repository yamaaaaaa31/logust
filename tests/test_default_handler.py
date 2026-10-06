"""The default console handler: stderr like loguru, colors auto-detected once.

Also covers ``disable()`` / ``enable()`` / ``set_level()`` on console handlers.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger

ESC = "\x1b["

COLOR_VARS = (
    "NO_COLOR",
    "FORCE_COLOR",
    "CI",
    "TRAVIS",
    "CIRCLECI",
    "APPVEYOR",
    "GITLAB_CI",
    "GITHUB_ACTIONS",
    "PYCHARM_HOSTED",
    "TERM",
)

CHILD = """
from logust import logger
logger.info("hello")
"""


def clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in COLOR_VARS}
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra)
    return env


def run(code: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=clean_env(**env),
        timeout=60,
    )


class TestStream:
    def test_writes_to_stderr_not_stdout(self) -> None:
        result = run(CHILD)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""
        assert "| INFO     |" in result.stderr
        assert result.stderr.endswith("- hello\n")

    def test_enable_after_remove_adds_a_stderr_handler(self) -> None:
        result = run(
            """
            from logust import logger
            logger.remove()
            logger.enable()
            logger.info("back")
            """
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""
        assert result.stderr.endswith("- back\n")


class TestColorDetection:
    def test_pipe_is_plain(self) -> None:
        result = run(CHILD)
        assert ESC not in result.stderr

    def test_force_color(self) -> None:
        result = run(CHILD, FORCE_COLOR="1")
        assert ESC in result.stderr

    def test_no_color_beats_force_color(self) -> None:
        result = run(CHILD, NO_COLOR="1", FORCE_COLOR="1")
        assert ESC not in result.stderr

    def test_empty_force_color_is_ignored(self) -> None:
        result = run(CHILD, FORCE_COLOR="")
        assert ESC not in result.stderr

    def test_known_ci(self) -> None:
        result = run(CHILD, CI="true", GITHUB_ACTIONS="true")
        assert ESC in result.stderr

    def test_ci_alone_is_not_enough(self) -> None:
        result = run(CHILD, CI="true")
        assert ESC not in result.stderr

    def test_pycharm(self) -> None:
        result = run(CHILD, PYCHARM_HOSTED="1")
        assert ESC in result.stderr

    def test_jupyter_kernel_stream(self) -> None:
        # An IPython kernel whose sys.stderr is an ipykernel OutStream renders colors.
        result = run(
            """
            import builtins, sys, types
            from logust import Logger
            from logust._logust import PyLogger

            iostream = types.ModuleType("ipykernel.iostream")

            class OutStream:
                def write(self, text):
                    pass

            iostream.OutStream = OutStream
            sys.modules["ipykernel.iostream"] = iostream
            builtins.__IPYTHON__ = True
            real_stderr = sys.stderr
            sys.stderr = OutStream()
            logger = Logger(PyLogger())
            sys.stderr = real_stderr
            logger.info("hello")
            """
        )
        assert result.returncode == 0, result.stderr
        assert ESC in result.stderr

    @pytest.mark.skipif(sys.platform == "win32", reason="needs a pty")
    @pytest.mark.parametrize(("term", "colored"), [("xterm-256color", True), ("dumb", False)])
    def test_terminal(self, term: str, colored: bool) -> None:
        import pty

        # The child waits on stdin until the line has been read: macOS drops
        # unread pty output once the child closes its end.
        child = CHILD + "import sys\nsys.stdin.readline()\n"
        leader, follower = pty.openpty()
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", child],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=follower,
                env=clean_env(TERM=term),
            )
            os.close(follower)
            output = b""
            while b"hello" not in output:
                chunk = os.read(leader, 4096)
                if not chunk:
                    break
                output += chunk
            stdout, _ = proc.communicate(b"go\n", timeout=60)
        finally:
            os.close(leader)
        assert proc.returncode == 0
        assert stdout == b""
        assert b"hello" in output
        assert (ESC.encode() in output) is colored


@pytest.fixture
def logger(monkeypatch: pytest.MonkeyPatch) -> Logger:
    for var in COLOR_VARS:
        monkeypatch.delenv(var, raising=False)
    return Logger(PyLogger(LogLevel.Trace))


class TestDisableEnable:
    def test_enable_restores_user_console_handlers(
        self, logger: Logger, capfd: pytest.CaptureFixture[str]
    ) -> None:
        logger.remove()
        handler_id = logger.add(sys.__stdout__, format="custom {message}", colorize=False)
        logger.disable()
        logger.info("hidden")
        logger.enable()
        logger.info("shown")
        out, err = capfd.readouterr()
        assert out == "custom shown\n"
        assert err == ""
        # Same handler, same id
        assert logger.remove(handler_id) is True
        logger.info("gone")
        assert capfd.readouterr() == ("", "")

    def test_enable_does_not_restore_a_removed_handler(
        self, logger: Logger, capfd: pytest.CaptureFixture[str]
    ) -> None:
        logger.remove()
        handler_id = logger.add(sys.__stdout__, format="custom {message}", colorize=False)
        logger.disable()
        assert logger.remove(handler_id) is True
        assert logger.remove(handler_id) is False
        logger.enable()  # No console handler left: the default one comes back
        logger.info("default")
        out, err = capfd.readouterr()
        assert out == ""
        assert err.endswith("- default\n")
        assert "custom" not in err

    def test_remove_all_drops_disabled_handlers(
        self, logger: Logger, capfd: pytest.CaptureFixture[str]
    ) -> None:
        logger.remove()
        logger.add(sys.__stdout__, format="custom {message}", colorize=False)
        logger.disable()
        logger.remove()
        logger.enable()
        logger.info("default")
        out, err = capfd.readouterr()
        assert out == ""
        assert err.endswith("- default\n")

    def test_disable_keeps_file_handlers(
        self, logger: Logger, capfd: pytest.CaptureFixture[str], tmp_path: os.PathLike[str]
    ) -> None:
        path = os.path.join(tmp_path, "app.log")
        logger.add(path, format="{message}")
        logger.disable()
        logger.info("to file")
        logger.complete()
        assert capfd.readouterr() == ("", "")
        with open(path, encoding="utf-8") as f:
            assert f.read() == "to file\n"

    def test_enable_level_applies_when_console_is_on(
        self, logger: Logger, capfd: pytest.CaptureFixture[str]
    ) -> None:
        logger.enable(level="WARNING")
        assert logger.get_level() == LogLevel.Warning
        logger.info("dropped")
        logger.warning("kept")
        _, err = capfd.readouterr()
        assert "dropped" not in err
        assert err.endswith("- kept\n")

    def test_enable_level_applies_to_restored_handlers(
        self, logger: Logger, capfd: pytest.CaptureFixture[str]
    ) -> None:
        logger.disable()
        logger.enable("ERROR")
        logger.warning("dropped")
        logger.error("kept")
        _, err = capfd.readouterr()
        assert "dropped" not in err
        assert err.endswith("- kept\n")

    def test_set_level_while_disabled(
        self, logger: Logger, capfd: pytest.CaptureFixture[str]
    ) -> None:
        logger.disable()
        logger.set_level("ERROR")
        logger.enable()
        logger.warning("dropped")
        logger.error("kept")
        _, err = capfd.readouterr()
        assert "dropped" not in err
        assert err.endswith("- kept\n")

    def test_bound_logger_shares_disabled_handlers(
        self, logger: Logger, capfd: pytest.CaptureFixture[str]
    ) -> None:
        bound = logger.bind(user="alice")
        bound.disable()
        logger.info("hidden")
        logger.enable()
        bound.info("shown")
        _, err = capfd.readouterr()
        assert "hidden" not in err
        assert err.endswith("- shown\n")
