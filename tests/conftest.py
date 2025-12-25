"""Shared test fixtures for logust tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger

# Global session-scoped logger to avoid the Rust library's global state corruption bug
_session_logger: Logger | None = None
_session_handler_id: int | None = None
_session_log_dir: Path | None = None


@pytest.fixture(scope="session")
def session_log_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a session-scoped temporary directory for logs."""
    global _session_log_dir
    _session_log_dir = tmp_path_factory.mktemp("logs")
    return _session_log_dir


@pytest.fixture(scope="session")
def session_logger(session_log_dir: Path) -> Generator[Logger, None, None]:
    """Create a single logger instance for the entire test session.

    This works around the Rust library's global state corruption bug
    where creating multiple PyLogger instances causes file handlers to fail.
    """
    global _session_logger, _session_handler_id

    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()

    _session_logger = logger

    yield logger

    logger.complete()
    logger.remove()


@pytest.fixture
def logger_with_file(
    session_logger: Logger, tmp_path: Path
) -> Generator[tuple[Logger, Path], None, None]:
    """Provide a logger with a file handler for each test.

    Uses the session-scoped logger but creates a new file handler for each test.
    Uses enqueue=False for synchronous writes to avoid race conditions in tests.
    """
    log_file = tmp_path / "test.log"

    handler_id = session_logger.add(log_file, level=LogLevel.Trace, enqueue=False)

    yield session_logger, log_file

    session_logger.complete()
    session_logger.remove(handler_id)


@pytest.fixture
def tmp_log_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for log files."""
    return tmp_path


@pytest.fixture
def fresh_logger() -> Generator[Logger, None, None]:
    """Create a fresh logger instance for each test.

    WARNING: Due to Rust library bug, creating multiple loggers may cause issues.
    Prefer using logger_with_file fixture when possible.
    """
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    yield logger
    logger.remove()


@pytest.fixture
def sample_log_file(tmp_path: Path) -> Path:
    """Create a sample log file for parsing tests."""
    log_file = tmp_path / "sample.log"
    log_file.write_text(
        "2024-01-01 10:00:00 | INFO | Message 1\n"
        "2024-01-01 10:00:01 | DEBUG | Message 2\n"
        "2024-01-01 10:00:02 | ERROR | Message 3\n"
    )
    return log_file


@pytest.fixture
def sample_json_log_file(tmp_path: Path) -> Path:
    """Create a sample JSON log file for parsing tests."""
    log_file = tmp_path / "sample.json"
    log_file.write_text(
        '{"level": "INFO", "message": "Message 1", "timestamp": "2024-01-01T10:00:00"}\n'
        '{"level": "DEBUG", "message": "Message 2", "timestamp": "2024-01-01T10:00:01"}\n'
        '{"level": "ERROR", "message": "Message 3", "timestamp": "2024-01-01T10:00:02"}\n'
    )
    return log_file
