"""Type definitions for logust.

This module provides TypedDict and Protocol definitions for type checking
log records, callbacks, and configuration dictionaries.
"""

from __future__ import annotations

import datetime
from typing import Any, NamedTuple, Protocol, TextIO, TypedDict

from ._record import RecordElapsed, RecordFile, RecordLevelStr, RecordProcess, RecordThread


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


class Level(NamedTuple):
    """Level information returned by ``logger.level()`` (loguru-compatible).

    Attributes:
        name: Level name (e.g., "INFO", "NOTICE").
        no: Numeric severity value.
        color: Color name used for console output (e.g., "green").
        icon: Icon symbol, or "" if none was set.
    """

    name: str
    no: int
    color: str
    icon: str


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
    """Log record dictionary passed to filters, patchers and ``add_callback`` callbacks.

    Shaped like loguru's record for the common fields while keeping logust's
    original keys: ``level`` and ``file`` are ``str`` subclasses, so code that
    compares them to strings keeps working.

    Attributes:
        level: Level name (``RecordLevelStr``, a ``str``) with loguru's
            ``.name``, ``.no`` and ``.icon``.
        level_no: Numeric log level value.
        message: The log message content.
        time: Aware ``datetime`` of the record (loguru's ``record["time"]``).
        timestamp: RFC 3339 formatted timestamp.
        elapsed: Time since logger start (``RecordElapsed``, a ``timedelta``
            whose ``str()`` is ``HH:MM:SS.mmm``).
        name: Module ``__name__`` of the caller.
        module: Caller file name without its extension.
        function: Caller function name.
        line: Caller line number.
        file: Caller file basename (``RecordFile``, a ``str``) with loguru's
            ``.name`` and ``.path``.
        file_path: Full caller file path (only on some formatted-sink records).
        thread: ``RecordThread`` with ``.id`` and ``.name``.
        thread_name: Thread name.
        thread_id: Thread ID.
        process: ``RecordProcess`` with ``.id`` and ``.name``.
        process_name: Process name.
        process_id: Process ID.
        exception: Formatted traceback text, or ``None``.
        extra: Additional context from bind().
    """

    level: RecordLevelStr
    level_no: int
    message: str
    time: datetime.datetime
    timestamp: str
    elapsed: RecordElapsed
    name: str
    module: str
    function: str
    line: int
    file: RecordFile
    file_path: str
    thread: RecordThread
    thread_name: str
    thread_id: int
    process: RecordProcess
    process_name: str
    process_id: int
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
        rotation: Rotation strategy ("daily", "hourly", "500 MB", or a
                  ``datetime.timedelta`` / ``datetime.time``).
                  Only valid for file sinks.
        retention: Retention policy ("10 days" or count as int).
                   Only valid for file sinks.
        compression: Compress rotated files: True (gzip) or a format string
                     ("gz", "bz2", "zip", "tar", "tar.gz", "tar.bz2").
                     Only valid for file sinks.
        serialize: Output as JSON instead of text format.
        filter: Filter callback function.
        enqueue: Enable async writes (default False).
                 Only valid for file sinks.
        colorize: Enable ANSI color codes for console sinks.
                  If not specified, auto-detect based on TTY.
        mode: "a" (append, default) or "w" (truncate on first open).
              Only valid for file sinks.
        encoding: UTF-8 aliases only; files are always written as UTF-8.
                  Only valid for file sinks.
        delay: Create the file when the first message is written.
               Only valid for file sinks.
        buffering: 1 (default) writes each line before the logging call
                   returns, N > 1 buffers up to N bytes. Only valid for
                   file sinks.
        catch: Sink error policy: None drops errors silently (default),
               True reports them to stderr, False raises them.
        backtrace: Show frames above the catch point in logged tracebacks.
        diagnose: Show variable values in logged tracebacks.
    """

    sink: str | TextIO
    level: str | int
    format: str
    rotation: str | datetime.timedelta | datetime.time
    retention: str | int
    compression: bool | str
    serialize: bool
    filter: FilterCallback
    enqueue: bool
    colorize: bool
    mode: str
    encoding: str
    delay: bool
    buffering: int
    catch: bool
    backtrace: bool
    diagnose: bool


class LevelConfig(TypedDict, total=False):
    """Configuration dict for logger.configure() custom levels.

    Attributes:
        name: Level name (e.g., "NOTICE"). Required.
        no: Numeric severity value. Required for a new level; omit it to
            update the color or icon of an existing level.
        color: Color name for terminal output.
        icon: Icon symbol for display.
    """

    name: str
    no: int
    color: str
    icon: str
