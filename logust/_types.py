"""Type definitions for logust.

This module provides TypedDict and Protocol definitions for type checking
log records, callbacks, and configuration dictionaries.
"""

from __future__ import annotations

from typing import Any, NamedTuple, Protocol, TextIO, TypedDict


class RecordLevel(NamedTuple):
    """Level information in a log record (loguru-compatible).

    Attributes:
        name: Level name (e.g., "INFO", "ERROR").
        no: Numeric severity value.
        icon: Icon symbol for display.
    """

    name: str
    no: int
    icon: str = ""


class RecordException(NamedTuple):
    """Exception information in a log record (loguru-compatible).

    Attributes:
        type: Exception class or None.
        value: Exception instance or None.
        traceback: Formatted traceback string or None.
    """

    type: type[BaseException] | None
    value: BaseException | None
    traceback: str | None


class LogRecord(TypedDict, total=False):
    """Log record dictionary passed to callbacks and filters.

    Compatible with loguru's Record type for common fields.

    Attributes:
        level: Log level name (e.g., "INFO", "ERROR").
        level_no: Numeric log level value.
        message: The log message content.
        timestamp: ISO 8601 formatted timestamp.
        exception: Exception traceback if present.
        extra: Additional context from bind().
    """

    level: str
    level_no: int
    message: str
    timestamp: str
    exception: str | None
    extra: dict[str, Any]


class FilterCallback(Protocol):
    """Protocol for filter callback functions.

    A filter callback receives a log record dictionary and returns
    True if the record should be logged, False to skip it.

    Example:
        >>> def my_filter(record: dict[str, Any]) -> bool:
        ...     return record.get("level") != "DEBUG"
        >>> logger.add("app.log", filter=my_filter)
    """

    def __call__(self, record: dict[str, Any]) -> bool: ...


class PatcherCallback(Protocol):
    """Protocol for patcher callback functions.

    A patcher callback receives a log record dictionary and modifies
    it in-place before the record is sent to handlers.

    Example:
        >>> def add_request_id(record: dict[str, Any]) -> None:
        ...     record["extra"]["request_id"] = get_current_request_id()
        >>> patched_logger = logger.patch(add_request_id)
    """

    def __call__(self, record: dict[str, Any]) -> None: ...


class LogCallback(Protocol):
    """Protocol for log record callback functions.

    A log callback receives a log record dictionary for processing
    (e.g., sending to external services, metrics collection).

    Example:
        >>> def send_to_sentry(record: dict[str, Any]) -> None:
        ...     if record.get("level") == "ERROR":
        ...         sentry_sdk.capture_message(record["message"])
        >>> logger.add_callback(send_to_sentry, level="ERROR")
    """

    def __call__(self, record: dict[str, Any]) -> None: ...


class HandlerConfig(TypedDict, total=False):
    """Configuration dict for logger.configure() handlers.

    Attributes:
        sink: File path or sys.stdout/sys.stderr for output (required).
        level: Minimum log level (name or numeric value).
        format: Custom format string.
        rotation: Rotation strategy ("daily", "hourly", "500 MB").
                  Only valid for file sinks.
        retention: Retention policy ("10 days" or count as int).
                   Only valid for file sinks.
        compression: Enable gzip compression for rotated files.
                     Only valid for file sinks.
        serialize: Output as JSON instead of text format.
        filter: Filter callback function.
        enqueue: Enable async writes (default True).
                 Only valid for file sinks.
        colorize: Enable ANSI color codes for console sinks.
                  If not specified, auto-detect based on TTY.
    """

    sink: str | TextIO
    level: str | int
    format: str
    rotation: str
    retention: str | int
    compression: bool
    serialize: bool
    filter: FilterCallback
    enqueue: bool
    colorize: bool


class LevelConfig(TypedDict, total=False):
    """Configuration dict for logger.configure() custom levels.

    Attributes:
        name: Level name (e.g., "NOTICE"). Required.
        no: Numeric severity value. Required.
        color: Color name for terminal output.
        icon: Icon symbol for display.
    """

    name: str
    no: int
    color: str
    icon: str
