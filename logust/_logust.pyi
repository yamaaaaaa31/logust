"""Type stubs for logust._logust Rust extension module."""

from collections.abc import Callable
from typing import Any

class LogLevel:
    """Log level enum with numeric ordering.

    Levels are ordered by severity:
    TRACE < DEBUG < INFO < SUCCESS < WARNING < ERROR < FAIL < CRITICAL
    """

    Trace: LogLevel
    Debug: LogLevel
    Info: LogLevel
    Success: LogLevel
    Warning: LogLevel
    Error: LogLevel
    Fail: LogLevel
    Critical: LogLevel

    @property
    def value(self) -> int:
        """Get numeric value for comparison."""
        ...

    @property
    def name(self) -> str:
        """Get display name."""
        ...

    def __eq__(self, other: object) -> bool: ...
    def __ne__(self, other: object) -> bool: ...
    def __lt__(self, other: LogLevel) -> bool: ...
    def __le__(self, other: LogLevel) -> bool: ...
    def __gt__(self, other: LogLevel) -> bool: ...
    def __ge__(self, other: LogLevel) -> bool: ...
    def __hash__(self) -> int: ...

class Rotation:
    """Rotation strategy enum for file handlers."""

    Never: Rotation
    Daily: Rotation
    Hourly: Rotation

    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...

class PyLogger:
    """Rust-implemented logger core.

    This class is the underlying Rust implementation wrapped by the
    Python Logger class. It handles all log record processing,
    handler management, and output formatting.
    """

    def __init__(self, level: LogLevel | None = None) -> None:
        """Create a new logger with optional default console level."""
        ...

    def add(
        self,
        path: str,
        level: LogLevel | None = None,
        format: str | None = None,
        rotation: str | None = None,
        retention: str | None = None,
        compression: bool | None = None,
        serialize: bool | None = None,
        filter: Callable[[dict[str, Any]], bool] | None = None,
        enqueue: bool | None = None,
    ) -> int:
        """Add a file handler and return its ID."""
        ...

    def add_console(
        self,
        stream: str,
        level: LogLevel | None = None,
        format: str | None = None,
        serialize: bool | None = None,
        filter: Callable[[dict[str, Any]], bool] | None = None,
        colorize: bool | None = None,
    ) -> int:
        """Add a console handler (stdout or stderr)."""
        ...

    def remove(self, handler_id: int | None = None) -> bool:
        """Remove a handler by ID, or all handlers if None."""
        ...

    def bind(self, kwargs: dict[str, Any] | None = None) -> PyLogger:
        """Create a new logger with bound context values."""
        ...

    def set_level(self, level: LogLevel) -> None:
        """Set minimum log level for all console handlers."""
        ...

    def get_level(self) -> LogLevel:
        """Get current minimum log level."""
        ...

    def is_level_enabled(self, level: LogLevel) -> bool:
        """Check if any handler would accept messages at the given level."""
        ...

    @property
    def min_level(self) -> int:
        """Get the cached minimum log level across all handlers and callbacks."""
        ...

    def enable(self, level: LogLevel | None = None) -> None:
        """Enable console output with given level."""
        ...

    def disable(self) -> None:
        """Disable console output."""
        ...

    def is_enabled(self) -> bool:
        """Check if console output is enabled."""
        ...

    def complete(self) -> None:
        """Flush all file handlers to ensure pending logs are written."""
        ...

    def add_callback(
        self,
        callback: Callable[[dict[str, Any]], None],
        level: LogLevel | None = None,
    ) -> int:
        """Add a callback to receive log records."""
        ...

    def remove_callback(self, callback_id: int) -> bool:
        """Remove a callback by ID."""
        ...

    def remove_callbacks(self, callback_ids: list[int]) -> int:
        """Remove multiple callbacks by IDs (batch operation).

        More efficient than calling remove_callback multiple times
        as it only updates caches once at the end.

        Returns:
            Number of callbacks actually removed.
        """
        ...

    @property
    def needs_caller_info(self) -> bool:
        """Check if any handler/callback needs caller info."""
        ...

    @property
    def needs_thread_info(self) -> bool:
        """Check if any handler/callback needs thread info."""
        ...

    @property
    def needs_process_info(self) -> bool:
        """Check if any handler/callback needs process info."""
        ...

    @property
    def needs_caller_info_for_handlers(self) -> bool:
        """Check if any handler format needs caller info (excludes callbacks)."""
        ...

    @property
    def needs_thread_info_for_handlers(self) -> bool:
        """Check if any handler format needs thread info (excludes callbacks)."""
        ...

    @property
    def needs_process_info_for_handlers(self) -> bool:
        """Check if any handler format needs process info (excludes callbacks)."""
        ...

    @property
    def handler_count(self) -> int:
        """Get the current number of handlers (excludes callbacks)."""
        ...

    def level(
        self,
        name: str,
        no: int,
        color: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Register a custom log level."""
        ...

    def log(
        self,
        level_arg: str | int,
        message: str,
        exception: str | None = None,
        name: str | None = None,
        function: str | None = None,
        line: int | None = None,
        file: str | None = None,
        thread_name: str | None = None,
        thread_id: int | None = None,
        process_name: str | None = None,
        process_id: int | None = None,
    ) -> None:
        """Log at any level (built-in or custom)."""
        ...

    def trace(
        self,
        message: str,
        exception: str | None = None,
        name: str | None = None,
        function: str | None = None,
        line: int | None = None,
        file: str | None = None,
        thread_name: str | None = None,
        thread_id: int | None = None,
        process_name: str | None = None,
        process_id: int | None = None,
    ) -> None:
        """Output TRACE level log message."""
        ...

    def debug(
        self,
        message: str,
        exception: str | None = None,
        name: str | None = None,
        function: str | None = None,
        line: int | None = None,
        file: str | None = None,
        thread_name: str | None = None,
        thread_id: int | None = None,
        process_name: str | None = None,
        process_id: int | None = None,
    ) -> None:
        """Output DEBUG level log message."""
        ...

    def info(
        self,
        message: str,
        exception: str | None = None,
        name: str | None = None,
        function: str | None = None,
        line: int | None = None,
        file: str | None = None,
        thread_name: str | None = None,
        thread_id: int | None = None,
        process_name: str | None = None,
        process_id: int | None = None,
    ) -> None:
        """Output INFO level log message."""
        ...

    def success(
        self,
        message: str,
        exception: str | None = None,
        name: str | None = None,
        function: str | None = None,
        line: int | None = None,
        file: str | None = None,
        thread_name: str | None = None,
        thread_id: int | None = None,
        process_name: str | None = None,
        process_id: int | None = None,
    ) -> None:
        """Output SUCCESS level log message."""
        ...

    def warning(
        self,
        message: str,
        exception: str | None = None,
        name: str | None = None,
        function: str | None = None,
        line: int | None = None,
        file: str | None = None,
        thread_name: str | None = None,
        thread_id: int | None = None,
        process_name: str | None = None,
        process_id: int | None = None,
    ) -> None:
        """Output WARNING level log message."""
        ...

    def error(
        self,
        message: str,
        exception: str | None = None,
        name: str | None = None,
        function: str | None = None,
        line: int | None = None,
        file: str | None = None,
        thread_name: str | None = None,
        thread_id: int | None = None,
        process_name: str | None = None,
        process_id: int | None = None,
    ) -> None:
        """Output ERROR level log message."""
        ...

    def fail(
        self,
        message: str,
        exception: str | None = None,
        name: str | None = None,
        function: str | None = None,
        line: int | None = None,
        file: str | None = None,
        thread_name: str | None = None,
        thread_id: int | None = None,
        process_name: str | None = None,
        process_id: int | None = None,
    ) -> None:
        """Output FAIL level log message."""
        ...

    def critical(
        self,
        message: str,
        exception: str | None = None,
        name: str | None = None,
        function: str | None = None,
        line: int | None = None,
        file: str | None = None,
        thread_name: str | None = None,
        thread_id: int | None = None,
        process_name: str | None = None,
        process_id: int | None = None,
    ) -> None:
        """Output CRITICAL level log message."""
        ...

logger: PyLogger
