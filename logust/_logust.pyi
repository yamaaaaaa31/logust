"""Type stubs for logust._logust Rust extension module."""

import datetime
from collections.abc import Callable
from contextvars import ContextVar, Token
from typing import Any, TypeAlias

from ._types import FilterType

_NativeFilter: TypeAlias = str | dict[str | None, str | int | bool] | None
"""A module name or a dict of minimum level per module, checked in Rust."""

CONTEXT_VAR: ContextVar[dict[str, Any] | None]
"""The ``contextualize()`` values of the current thread or task (unset outside a block)."""

def set_context(value: dict[str, Any] | None) -> Token[dict[str, Any] | None]:
    """``CONTEXT_VAR.set(value)``, also marking ``contextualize()`` as in use for the fast path."""
    ...

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

    def __init__(self, level: LogLevel | str | int | None = None) -> None:
        """Create a new logger with a default console handler on stderr.

        Colors are detected once, here (TTY, NO_COLOR, FORCE_COLOR, CI,
        PyCharm, Jupyter), like ``add(sys.stderr)``.
        """
        ...

    def add(
        self,
        path: str,
        level: LogLevel | str | int | None = None,
        format: str | None = None,
        rotation: str | None = None,
        retention: str | None = None,
        compression: bool | str | None = None,
        serialize: bool | None = None,
        filter: FilterType = None,
        enqueue: bool | None = None,
        colorize: bool | None = None,
        mode: str | None = None,
        delay: bool | None = None,
        catch: bool | None = None,
        buffering: int | None = None,
    ) -> int:
        """Add a file handler and return its ID.

        ``compression`` accepts a bool (``True`` = gzip) or one of
        ``"gz"``, ``"bz2"``, ``"zip"``, ``"tar"``, ``"tar.gz"``, ``"tar.bz2"``.
        ``mode`` is ``"a"`` (default) or ``"w"``. ``catch``: ``None`` drops
        write errors, ``True`` reports them to stderr, ``False`` raises.
        ``buffering``: ``None`` (default) buffers 8 KB (each line with
        rotation), ``1`` writes each line, ``N > 1`` buffers up to ``N``
        bytes, negative means 8192, ``0`` raises ``ValueError``.
        ``filter`` is a module name, a dict of minimum level per module (both
        checked in Rust) or a callable that receives the record dict.
        """
        ...

    def add_console(
        self,
        stream: str,
        level: LogLevel | str | int | None = None,
        format: str | None = None,
        serialize: bool | None = None,
        filter: FilterType = None,
        colorize: bool | None = None,
        catch: bool | None = None,
    ) -> int:
        """Add a console handler (stdout or stderr)."""
        ...

    def remove(self, handler_id: int | None = None) -> bool:
        """Remove a handler by ID, or all handlers if None."""
        ...

    def bind(self, kwargs: dict[str, Any] | None = None) -> PyLogger:
        """Create a new logger with bound context values."""
        ...

    def contextualized(
        self, context: dict[str, Any], extra: dict[str, Any] | None = None
    ) -> PyLogger:
        """Logger for one message inside ``contextualize()``: ``context`` under this
        logger's bound values, with the message's ``extra`` kwargs on top.
        """
        ...

    def set_level(self, level: LogLevel | str | int) -> None:
        """Set minimum log level for all console handlers."""
        ...

    def get_level(self) -> LogLevel | int:
        """Get current minimum log level."""
        ...

    def is_level_enabled(self, level: LogLevel | str | int) -> bool:
        """Check if any handler would accept messages at the given level."""
        ...

    @property
    def min_level(self) -> int:
        """Get the cached minimum log level across all handlers and callbacks."""
        ...

    def enable(self, level: LogLevel | str | int | None = None) -> None:
        """Put back the console handlers ``disable()`` set aside, or add the default one.

        ``level``, when given, becomes the level of every console handler.
        """
        ...

    def disable(self) -> None:
        """Set every console handler aside until ``enable()``."""
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
        level: LogLevel | str | int | None = None,
        file_path: bool = False,
        raise_errors: bool = False,
        extra_repr: bool = False,
        filter: _NativeFilter = None,
    ) -> int:
        """Add a callback to receive log records.

        file_path adds the caller's source file path as ``file_path`` to the records,
        and extra_repr the extra dict rendered for ``{extra}`` as ``extra_repr``.
        With ``raise_errors=True`` an exception raised by the callback
        propagates to the logging call; otherwise it is dropped.
        """
        ...

    def add_serialized_callback(
        self,
        callback: Callable[[dict[str, Any]], None],
        level: LogLevel | str | int | None = None,
        raise_errors: bool = False,
        filter: _NativeFilter = None,
    ) -> int:
        """Add a serialized callable sink with typed JSON extras."""
        ...

    def add_formatted_sink_callback(
        self,
        callback: Callable[[dict[str, Any]], None],
        requirements: tuple[bool, ...],
        extra_keys: tuple[str, ...],
        level: LogLevel | str | int | None = None,
        raise_errors: bool = False,
        filter: _NativeFilter = None,
    ) -> int:
        """Add a formatted callable sink (minimal record dict for templates)."""
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

    def try_resolve_emit_level_no(self, level_arg: str | int | LogLevel) -> int | None:
        """Resolve level name or numeric ``no`` to registered severity (``LevelInfo.no``)."""
        ...

    def needs_caller_info_for_emit_no(self, emit_no: int) -> bool:
        """Whether caller info is needed when emitting at numeric severity ``emit_no``."""
        ...

    def needs_thread_info_for_emit_no(self, emit_no: int) -> bool: ...
    def needs_process_info_for_emit_no(self, emit_no: int) -> bool: ...
    def collect_needs_for_emit_no(self, emit_no: int) -> tuple[bool, bool, bool]:
        """``(needs_caller, needs_thread, needs_process)`` after full merge at ``emit_no``."""
        ...

    def handler_only_needs_for_emit_no(self, emit_no: int) -> tuple[bool, bool, bool]:
        """Handler formats only (no callbacks), merged for handlers eligible at ``emit_no``."""
        ...

    @property
    def handler_count(self) -> int:
        """Get the current number of handlers (excludes callbacks)."""
        ...

    def set_fast_collect(self, table: int, generation: int, owner: int) -> bool:
        """What ``log_fast`` collects per built-in level (one nibble each, slot order
        TRACE..CRITICAL): bit 0 caller, bit 1 thread, bit 2 process, bit 3 "use the
        Python path". Stored only if ``generation`` is still current (returns
        False otherwise); ``owner`` is the Logger family the table belongs to.
        """
        ...

    def invalidate_fast_collect(self) -> int:
        """Reset the ``log_fast`` table and return its new generation."""
        ...

    def log_fast(self, level_no: int, message: object, depth: int, owner: int, /) -> bool:
        """Log ``message`` at built-in level ``level_no`` from the caller ``depth``
        frames above the calling Python frame, collecting caller/thread/process
        info in Rust. Returns False (without logging) when the Python path must
        be used instead.
        """
        ...

    def with_colors(self, colors: bool) -> PyLogger:
        """Same logger, rendering (True) or not parsing (False) message color markup."""
        ...

    def set_exception_variant(self, handler_id: int, variant: int) -> bool:
        """Set a handler's traceback variant (bit 0: backtrace, bit 1: diagnose)."""
        ...

    @property
    def exception_variant_mask(self) -> int:
        """Bit ``v`` is set when a handler or callable sink uses traceback variant ``v``."""
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

    def level_info(self, name: str) -> tuple[str, int, str, str | None] | None:
        """Look up a level by name: ``(name, no, color, icon)``, or None if unknown."""
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

def apply_color_markup(text: str, colorize: bool, base: str = "") -> str:
    """Render known color markup tags as ANSI codes, or strip them if not colorize.

    base is the ANSI prefix of styles surrounding text; it is re-applied after each reset.
    """
    ...

def colorize_level(text: str, level: str) -> str:
    """Style text in the bold color of the named level."""
    ...

def split_format_markup(template: str) -> list[tuple[str, str]]:
    """Split color markup out of a format template into (kind, value) pieces.

    kind is "text", "open" (value is the ANSI prefix), "level", or "close".
    """
    ...

def level_style(level: str) -> str:
    """ANSI prefix that styles text in the bold color of the named level."""
    ...

def level_details(level: str) -> tuple[int, str] | None:
    """(no, icon) of the named level (icon is "" if it has none), or None if unknown."""
    ...

def _flush_file_sinks_at_exit() -> None:
    """Drain ``enqueue=True`` and flush buffered file sinks (``atexit``, at import)."""
    ...

def record_time_fields() -> tuple[datetime.datetime, str, datetime.timedelta]:
    """(time, timestamp, elapsed) for the current instant, shaped like a filter record's."""
    ...

class TimeFormatter:
    """A compiled loguru ``{time:<spec>}`` format."""

    def __init__(self, spec: str) -> None:
        """Compile spec; raises ValueError if it is invalid."""
        ...

    def format_rfc3339(self, timestamp: str) -> str:
        """Format an RFC 3339 timestamp; unparsable input is returned unchanged."""
        ...

logger: PyLogger
