"""Tests for caller information feature."""

import json
import subprocess
import sys


class TestCallerInfo:
    """Tests for caller info (name, function, line) in log output."""

    def test_caller_info_basic(self, tmp_path):
        """Test that caller info is captured correctly in file output."""
        log_file = tmp_path / "test.log"
        code = f"""
from logust import logger
logger.remove()
logger.add({str(log_file)!r}, format="{{name}}:{{function}}:{{line}} - {{message}}")
def my_func():
    logger.info("test message")
my_func()
logger.complete()
"""
        subprocess.run([sys.executable, "-c", code], check=True)

        content = log_file.read_text()
        assert "__main__:my_func:" in content
        assert "test message" in content

    def test_caller_info_in_json(self, tmp_path):
        """Test that caller info is included in JSON output."""
        log_file = tmp_path / "test.json"
        code = f"""
from logust import logger
logger.remove()
logger.add({str(log_file)!r}, serialize=True)
def my_func():
    logger.info("json test")
my_func()
logger.complete()
"""
        subprocess.run([sys.executable, "-c", code], check=True)

        content = log_file.read_text().strip()
        record = json.loads(content)
        assert record["name"] == "__main__"
        assert record["function"] == "my_func"
        assert isinstance(record["line"], int)
        assert record["line"] > 0


class TestCallerDepth:
    """Tests for depth adjustment in caller info."""

    def test_direct_call_shows_caller(self, tmp_path):
        """Direct log call should show the actual caller function."""
        log_file = tmp_path / "test.log"
        code = f"""
from logust import logger
logger.remove()
logger.add({str(log_file)!r}, format="{{function}} - {{message}}")
def actual_caller():
    logger.info("direct call")
actual_caller()
logger.complete()
"""
        subprocess.run([sys.executable, "-c", code], check=True)

        content = log_file.read_text()
        assert "actual_caller - direct call" in content

    def test_opt_preserves_caller(self, tmp_path):
        """opt() should not affect caller info when depth=0."""
        log_file = tmp_path / "test.log"
        code = f"""
from logust import logger
logger.remove()
logger.add({str(log_file)!r}, format="{{function}} - {{message}}")
def test_func():
    logger.opt().info("through opt")
test_func()
logger.complete()
"""
        subprocess.run([sys.executable, "-c", code], check=True)

        content = log_file.read_text()
        assert "test_func - through opt" in content

    def test_opt_depth_adjusts_caller(self, tmp_path):
        """opt(depth=N) should skip N frames."""
        log_file = tmp_path / "test.log"
        code = f"""
from logust import logger
logger.remove()
logger.add({str(log_file)!r}, format="{{function}} - {{message}}")
def wrapper():
    def inner():
        logger.opt(depth=1).info("with depth=1")
    inner()
wrapper()
logger.complete()
"""
        subprocess.run([sys.executable, "-c", code], check=True)

        content = log_file.read_text()
        # Should show 'wrapper', not 'inner'
        assert "wrapper - with depth=1" in content

    def test_exception_shows_caller(self, tmp_path):
        """exception() should show the caller, not internal methods."""
        log_file = tmp_path / "test.log"
        code = f"""
from logust import logger
logger.remove()
logger.add({str(log_file)!r}, format="{{function}} - {{message}}")
def my_exception_handler():
    try:
        raise ValueError("test")
    except ValueError:
        logger.exception("caught error")
my_exception_handler()
logger.complete()
"""
        subprocess.run([sys.executable, "-c", code], check=True)

        content = log_file.read_text()
        assert "my_exception_handler - caught error" in content

    def test_catch_decorator_shows_call_site(self, tmp_path):
        """catch decorator should show where decorated function was called."""
        log_file = tmp_path / "test.log"
        code = f"""
from logust import logger
logger.remove()
logger.add({str(log_file)!r}, format="{{function}} - {{message}}")

@logger.catch()
def risky_func():
    raise RuntimeError("oops")

def caller_of_risky():
    risky_func()

caller_of_risky()
logger.complete()
"""
        subprocess.run([sys.executable, "-c", code], check=True)

        content = log_file.read_text()
        # Should show caller_of_risky as the call site
        assert "caller_of_risky -" in content
        assert "An error occurred: oops" in content


class TestConsoleSink:
    """Tests for stdout/stderr as sinks."""

    def test_add_stdout_sink(self):
        """Test adding sys.stdout as sink outputs to stdout."""
        code = """
import sys
from logust import logger
logger.remove()
logger.add(sys.stdout, colorize=False, format="{message}")
logger.info("stdout test")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        assert "stdout test" in result.stdout
        assert result.stderr == ""

    def test_add_stderr_sink(self):
        """Test adding sys.stderr as sink outputs to stderr."""
        code = """
import sys
from logust import logger
logger.remove()
logger.add(sys.stderr, colorize=False, format="{message}")
logger.info("stderr test")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        assert "stderr test" in result.stderr
        assert result.stdout == ""

    def test_console_with_serialize(self):
        """Test JSON output to console."""
        code = """
import sys
from logust import logger
logger.remove()
logger.add(sys.stdout, serialize=True)
logger.info("json test")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        assert '"message":"json test"' in result.stdout
        assert '"level":"INFO"' in result.stdout

    def test_multiple_console_handlers(self):
        """Test multiple console handlers with different settings."""
        code = """
import sys
from logust import logger
logger.remove()
logger.add(sys.stdout, colorize=False, format="{message}")
logger.add(sys.stderr, serialize=True)
logger.info("multi test")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        # stdout gets formatted output
        assert "multi test" in result.stdout
        # stderr gets JSON
        assert '"message":"multi test"' in result.stderr


class TestColorize:
    """Tests for colorize parameter."""

    def test_colorize_true_includes_ansi(self):
        """Test that colorize=True includes ANSI codes."""
        code = """
import sys
from logust import logger
logger.remove()
logger.add(sys.stdout, colorize=True)
logger.info("color test")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        # Check for ANSI escape codes
        assert "\x1b[" in result.stdout

    def test_colorize_false_no_ansi(self):
        """Test that colorize=False excludes ANSI codes."""
        code = """
import sys
from logust import logger
logger.remove()
logger.add(sys.stdout, colorize=False)
logger.info("no color test")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        assert "\x1b[" not in result.stdout
        assert "no color test" in result.stdout

    def test_serialize_no_ansi(self):
        """Test that serialize=True outputs plain JSON without ANSI."""
        code = """
import sys
from logust import logger
logger.remove()
logger.add(sys.stdout, serialize=True)
logger.info("json test")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        # JSON should not have ANSI codes
        assert "\x1b[" not in result.stdout
        assert '"message":"json test"' in result.stdout


class TestPerformance:
    """Tests for performance optimizations."""

    def test_disabled_level_skips_frame_capture(self, tmp_path):
        """Test that disabled levels don't capture frame info (perf optimization)."""
        # This is more of a behavioral test - we can't directly measure frame capture
        # but we can verify the level check works
        log_file = tmp_path / "test.log"
        code = f"""
from logust import logger
logger.remove()
# Add handler with WARNING level
logger.add({str(log_file)!r}, level="WARNING", format="{{message}}")
# These should be skipped (level check before frame capture)
logger.debug("debug msg")
logger.info("info msg")
# This should be logged
logger.warning("warning msg")
logger.complete()
"""
        subprocess.run([sys.executable, "-c", code], check=True)

        content = log_file.read_text()
        assert "debug msg" not in content
        assert "info msg" not in content
        assert "warning msg" in content
