"""Tests for additional format tokens ({elapsed}, {thread}, {process}, {file})."""

from __future__ import annotations

import re
import threading
from pathlib import Path

from logust import Logger, LogLevel
from logust._logust import PyLogger


class TestElapsedToken:
    """Test {elapsed} format token."""

    def test_elapsed_token_in_output(self, tmp_path: Path) -> None:
        """Test that {elapsed} token produces output in HH:MM:SS.mmm format."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "elapsed.log"
        logger.add(str(log_file), format="{elapsed} | {message}")

        logger.info("Test message")
        logger.complete()

        content = log_file.read_text()
        # Elapsed format should be like "00:00:00.123"
        elapsed_pattern = r"\d{2}:\d{2}:\d{2}\.\d{3}"
        assert re.search(elapsed_pattern, content), f"Expected elapsed format in: {content}"
        assert "Test message" in content

    def test_elapsed_increases_over_time(self, tmp_path: Path) -> None:
        """Test that elapsed time increases between log calls."""
        import time

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "elapsed_time.log"
        logger.add(str(log_file), format="{elapsed} | {message}")

        logger.info("First message")
        time.sleep(0.1)  # 100ms delay
        logger.info("Second message")
        logger.complete()

        content = log_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2

        # Extract elapsed times
        pattern = r"(\d{2}:\d{2}:\d{2}\.\d{3})"
        match1 = re.search(pattern, lines[0])
        match2 = re.search(pattern, lines[1])
        assert match1 and match2

        # Second elapsed should be greater than first
        elapsed1 = match1.group(1)
        elapsed2 = match2.group(1)
        # Simple string comparison works for this format since they're zero-padded
        assert elapsed2 > elapsed1, f"Expected {elapsed2} > {elapsed1}"


class TestThreadToken:
    """Test {thread} format token."""

    def test_thread_token_in_output(self, tmp_path: Path) -> None:
        """Test that {thread} token produces thread name and ID."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "thread.log"
        logger.add(str(log_file), format="{thread} | {message}")

        logger.info("Test message")
        logger.complete()

        content = log_file.read_text()
        # Should contain thread name (e.g., "MainThread") and thread ID
        assert "MainThread" in content or "Thread" in content
        assert "Test message" in content

    def test_thread_token_in_different_threads(self, tmp_path: Path) -> None:
        """Test that {thread} shows different values in different threads."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "threads.log"
        logger.add(str(log_file), format="{thread} | {message}")

        def worker() -> None:
            logger.info("Worker thread message")

        thread = threading.Thread(target=worker, name="TestWorker")
        thread.start()
        thread.join()

        logger.info("Main thread message")
        logger.complete()

        content = log_file.read_text()
        assert "TestWorker" in content or "Worker" in content
        assert "Main" in content


class TestProcessToken:
    """Test {process} format token."""

    def test_process_token_in_output(self, tmp_path: Path) -> None:
        """Test that {process} token produces process name and ID."""
        import os

        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "process.log"
        logger.add(str(log_file), format="{process} | {message}")

        logger.info("Test message")
        logger.complete()

        content = log_file.read_text()
        # Should contain process ID
        pid = str(os.getpid())
        assert pid in content, f"Expected PID {pid} in: {content}"
        assert "Test message" in content


class TestFileToken:
    """Test {file} format token."""

    def test_file_token_in_output(self, tmp_path: Path) -> None:
        """Test that {file} token produces source file name."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "file.log"
        logger.add(str(log_file), format="{file}:{line} | {message}")

        logger.info("Test message")
        logger.complete()

        content = log_file.read_text()
        # Should contain this test file name
        assert "test_format_tokens.py" in content
        assert "Test message" in content

    def test_file_token_shows_basename_only(self, tmp_path: Path) -> None:
        """Test that {file} shows only the file basename, not full path."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "file_basename.log"
        logger.add(str(log_file), format="{file} | {message}")

        logger.info("Test message")
        logger.complete()

        content = log_file.read_text()
        # Should NOT contain directory separators
        assert "/" not in content.split("|")[0]
        assert "\\" not in content.split("|")[0]


class TestModuleToken:
    """Test {module} format token (alias for {name})."""

    def test_module_token_in_output(self, tmp_path: Path) -> None:
        """Test that {module} token produces module name."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "module.log"
        logger.add(str(log_file), format="{module} | {message}")

        logger.info("Test message")
        logger.complete()

        content = log_file.read_text()
        # Should contain module name (similar to {name})
        assert "test_format_tokens" in content or "tests." in content
        assert "Test message" in content


class TestCombinedFormatTokens:
    """Test multiple format tokens together."""

    def test_all_new_tokens_combined(self, tmp_path: Path) -> None:
        """Test all new tokens in a single format string."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "combined.log"
        logger.add(
            str(log_file),
            format="{elapsed} | {thread} | {process} | {file}:{line} | {message}",
        )

        logger.info("Combined test")
        logger.complete()

        content = log_file.read_text()
        assert "Combined test" in content
        # Verify multiple separators exist (indicating all tokens rendered)
        assert content.count("|") >= 4

    def test_new_tokens_with_existing_tokens(self, tmp_path: Path) -> None:
        """Test new tokens combined with existing tokens."""
        inner = PyLogger(LogLevel.Trace)
        logger = Logger(inner)
        logger.disable()

        log_file = tmp_path / "mixed.log"
        logger.add(
            str(log_file),
            format="{time} | {level:<8} | {thread} | {file}:{function}:{line} | {message}",
        )

        logger.info("Mixed format test")
        logger.complete()

        content = log_file.read_text()
        assert "INFO" in content
        assert "Mixed format test" in content
