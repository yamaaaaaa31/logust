"""Logust - A fast, Rust-powered Python logging library inspired by loguru.

Version: 0.1.0

Usage:
    >>> import logust
    >>> logust.info("Hello, world!")

    >>> from logust import logger
    >>> logger.debug("Debug message")
    >>> logger.info("Info message")
    >>> logger.warning("Warning message")
    >>> logger.error("Error message")

    >>> # Add file handler
    >>> logger.add("app.log", rotation="500 MB", retention="10 days")

    >>> # Bind context
    >>> user_logger = logger.bind(user_id="123")
    >>> user_logger.info("User action")

    >>> # Custom levels
    >>> logger.level("NOTICE", no=25, color="cyan")
    >>> logger.log("NOTICE", "Custom level message")

    >>> # Color markup
    >>> logger.info("<red>Error</red> in <blue>module</blue>")

    >>> # Parse log files
    >>> from logust import parse
    >>> for record in parse("app.log", r"(?P<level>\\w+) \\| (?P<message>.*)"):
    ...     print(record)

Integrations (logust.contrib):
    >>> # Redirect standard logging to logust
    >>> from logust.contrib import intercept_logging
    >>> intercept_logging()

    >>> # Function timing decorators
    >>> from logust.contrib import log_fn, debug_fn
    >>> @log_fn
    ... def my_function(): ...

    >>> # FastAPI/Starlette middleware
    >>> from logust.contrib import RequestLoggerMiddleware
    >>> app.add_middleware(RequestLoggerMiddleware)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._logger import CallerInfo, CollectOptions, Logger, ProcessInfo, ThreadInfo
from ._logust import LogLevel, PyLogger, Rotation
from ._logust import logger as _rust_logger
from ._opt import OptLogger
from ._parse import parse, parse_json
from ._types import (
    FilterCallback,
    HandlerConfig,
    LevelConfig,
    LogCallback,
    LogRecord,
    PatcherCallback,
    RecordException,
    RecordLevel,
)

if TYPE_CHECKING:

    def trace(message: str, *, exception: str | None = None, **kwargs: Any) -> None: ...
    def debug(message: str, *, exception: str | None = None, **kwargs: Any) -> None: ...
    def info(message: str, *, exception: str | None = None, **kwargs: Any) -> None: ...
    def success(message: str, *, exception: str | None = None, **kwargs: Any) -> None: ...
    def warning(message: str, *, exception: str | None = None, **kwargs: Any) -> None: ...
    def error(message: str, *, exception: str | None = None, **kwargs: Any) -> None: ...
    def fail(message: str, *, exception: str | None = None, **kwargs: Any) -> None: ...
    def critical(message: str, *, exception: str | None = None, **kwargs: Any) -> None: ...


__version__ = "0.2.1"

logger = Logger(_rust_logger)


def __getattr__(name: str) -> Any:
    if hasattr(logger, name):
        return getattr(logger, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CallerInfo",
    "CollectOptions",
    "FilterCallback",
    "HandlerConfig",
    "LevelConfig",
    "LogCallback",
    "LogLevel",
    "LogRecord",
    "Logger",
    "OptLogger",
    "PatcherCallback",
    "ProcessInfo",
    "PyLogger",
    "RecordException",
    "RecordLevel",
    "Rotation",
    "ThreadInfo",
    "__version__",
    "logger",
    "parse",
    "parse_json",
]
