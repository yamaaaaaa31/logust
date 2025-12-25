"""Logger class - main logging interface."""

from __future__ import annotations

import functools
import os
import sys
import traceback
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TextIO

from ._logust import LogLevel, PyLogger

if TYPE_CHECKING:
    from ._opt import OptLogger


def _get_caller_info(depth: int = 1) -> tuple[str, str, int]:
    """Get caller information (module name, function name, line number).

    Args:
        depth: Number of frames to go back from the caller of this function

    Returns:
        Tuple of (module_name, function_name, line_number)
    """
    try:
        frame = sys._getframe(depth + 1)  # +1 to skip this function itself
        code = frame.f_code
        # Get module name from globals, or use filename as fallback
        module_name = frame.f_globals.get("__name__", code.co_filename)
        return (module_name, code.co_name, frame.f_lineno)
    except (ValueError, AttributeError):
        return ("", "", 0)


def _to_log_level(level: LogLevel | str) -> LogLevel:
    """Convert string level name to LogLevel enum."""
    if isinstance(level, str):
        return getattr(LogLevel, level.capitalize())  # type: ignore[no-any-return]
    return level


try:
    _LEVEL_VALUES: dict[str, int] = {
        "trace": LogLevel.Trace.value,
        "debug": LogLevel.Debug.value,
        "info": LogLevel.Info.value,
        "success": LogLevel.Success.value,
        "warning": LogLevel.Warning.value,
        "error": LogLevel.Error.value,
        "fail": LogLevel.Fail.value,
        "critical": LogLevel.Critical.value,
    }
except (AttributeError, TypeError):
    import warnings

    warnings.warn(
        "LogLevel enum access failed, using static fallback values",
        RuntimeWarning,
        stacklevel=1,
    )
    _LEVEL_VALUES = {
        "trace": 5,
        "debug": 10,
        "info": 20,
        "success": 25,
        "warning": 30,
        "error": 40,
        "fail": 45,
        "critical": 50,
    }

_LEVEL_VALUE_MAP: dict[int, str] = {v: k for k, v in _LEVEL_VALUES.items()}
if len(_LEVEL_VALUE_MAP) != len(_LEVEL_VALUES):
    raise ValueError("Duplicate numeric level values detected")


class Logger:
    """Main logger class wrapping the Rust PyLogger.

    Provides a loguru-compatible API for logging with support for:
    - Multiple log levels (trace, debug, info, success, warning, error, fail, critical)
    - File handlers with rotation and retention
    - Context binding
    - Exception catching
    - Callbacks
    - Custom log levels
    - Record patching
    """

    def __init__(
        self,
        inner: PyLogger,
        patchers: list[Callable[[dict[str, Any]], None]] | None = None,
    ) -> None:
        self._inner = inner
        self._patchers = patchers or []

    def _log_with_level(
        self,
        level_value: int,
        level_name: str,
        message: str,
        exception: str | None,
        depth: int,
    ) -> None:
        if level_value < self._inner.min_level:
            return
        name, function, line = _get_caller_info(depth + 1)
        getattr(self._inner, level_name)(
            str(message), exception=exception, name=name, function=function, line=line
        )

    def trace(
        self, message: str, *, exception: str | None = None, _depth: int = 0, **kwargs: Any
    ) -> None:
        """Output TRACE level log message."""
        self._log_with_level(5, "trace", message, exception, _depth + 1)

    def debug(
        self, message: str, *, exception: str | None = None, _depth: int = 0, **kwargs: Any
    ) -> None:
        """Output DEBUG level log message."""
        self._log_with_level(10, "debug", message, exception, _depth + 1)

    def info(
        self, message: str, *, exception: str | None = None, _depth: int = 0, **kwargs: Any
    ) -> None:
        """Output INFO level log message."""
        self._log_with_level(20, "info", message, exception, _depth + 1)

    def success(
        self, message: str, *, exception: str | None = None, _depth: int = 0, **kwargs: Any
    ) -> None:
        """Output SUCCESS level log message."""
        self._log_with_level(25, "success", message, exception, _depth + 1)

    def warning(
        self, message: str, *, exception: str | None = None, _depth: int = 0, **kwargs: Any
    ) -> None:
        """Output WARNING level log message."""
        self._log_with_level(30, "warning", message, exception, _depth + 1)

    def error(
        self, message: str, *, exception: str | None = None, _depth: int = 0, **kwargs: Any
    ) -> None:
        """Output ERROR level log message."""
        self._log_with_level(40, "error", message, exception, _depth + 1)

    def fail(
        self, message: str, *, exception: str | None = None, _depth: int = 0, **kwargs: Any
    ) -> None:
        """Output FAIL level log message."""
        self._log_with_level(45, "fail", message, exception, _depth + 1)

    def critical(
        self, message: str, *, exception: str | None = None, _depth: int = 0, **kwargs: Any
    ) -> None:
        """Output CRITICAL level log message."""
        self._log_with_level(50, "critical", message, exception, _depth + 1)

    def exception(self, message: str, *, _depth: int = 0, **kwargs: Any) -> None:
        """Log ERROR with current exception traceback.

        Must be called from within an except block to capture the exception.
        If called outside an except block, logs a plain ERROR message.

        Args:
            message: The error message.
            _depth: Internal depth adjustment for wrapper methods.
            **kwargs: Additional arguments passed to error().

        Examples:
            >>> try:
            ...     risky_operation()
            ... except:
            ...     logger.exception("Operation failed")
            # Output: ERROR with full traceback
        """
        exc_info = sys.exc_info()
        if exc_info[0] is not None:
            tb = traceback.format_exc()
            self.error(message, exception=tb, _depth=_depth + 1, **kwargs)
        else:
            self.error(message, _depth=_depth + 1, **kwargs)

    def level(
        self,
        name: str,
        *,
        no: int,
        color: str | None = None,
        icon: str | None = None,
    ) -> None:
        """Register a custom log level.

        Args:
            name: Level name (e.g., "NOTICE"). Case-insensitive.
            no: Numeric severity (higher = more severe).
                Built-in levels: TRACE=5, DEBUG=10, INFO=20, SUCCESS=25,
                WARNING=30, ERROR=40, FAIL=45, CRITICAL=50
            color: Color name (e.g., "cyan", "bright_blue", "red").
            icon: Optional icon symbol for display.

        Examples:
            >>> logger.level("NOTICE", no=25, color="cyan", icon="...")
            >>> logger.log("NOTICE", "Custom level message")
        """
        self._inner.level(name, no, color, icon)

    def log(
        self,
        level: str | int,
        message: str,
        *,
        exception: str | None = None,
        _depth: int = 0,
        **kwargs: Any,
    ) -> None:
        """Log at any level (built-in or custom).

        Args:
            level: Level name (str) or numeric value (int).
            message: Log message.
            exception: Optional exception traceback.
            _depth: Internal depth adjustment for wrapper methods.

        Examples:
            >>> logger.log("INFO", "Using built-in level by name")
            >>> logger.log(20, "Using built-in level by number")
        """
        if isinstance(level, str):
            level_lower = level.lower()
            if level_lower in _LEVEL_VALUES:
                self._log_with_level(
                    _LEVEL_VALUES[level_lower], level_lower, message, exception, _depth + 1
                )
                return
        elif isinstance(level, int) and level in _LEVEL_VALUE_MAP:
            self._log_with_level(
                level, _LEVEL_VALUE_MAP[level], message, exception, _depth + 1
            )
            return

        name, function, line = _get_caller_info(_depth + 1)
        self._inner.log(
            level, str(message), exception=exception, name=name, function=function, line=line
        )

    def set_level(self, level: LogLevel | str) -> None:
        """Set minimum log level for console output."""
        self._inner.set_level(_to_log_level(level))

    def get_level(self) -> LogLevel:
        """Get current minimum log level."""
        return self._inner.get_level()

    def is_level_enabled(self, level: LogLevel | str) -> bool:
        """Check if any handler would accept messages at the given level.

        Args:
            level: Log level to check.

        Returns:
            True if at least one handler would process messages at this level.
        """
        return self._inner.is_level_enabled(_to_log_level(level))

    def enable(self, level: LogLevel | str | None = None) -> None:
        """Enable console logging."""
        self._inner.enable(_to_log_level(level) if level is not None else None)

    def disable(self) -> None:
        """Disable console logging."""
        self._inner.disable()

    def is_enabled(self) -> bool:
        """Check if console logging is enabled."""
        return self._inner.is_enabled()

    def complete(self) -> None:
        """Flush all file handlers to ensure pending logs are written.

        Call this before program exit to ensure all logs are persisted.

        Examples:
            >>> logger.info("Final message")
            >>> logger.complete()  # Ensure message is written to files
        """
        self._inner.complete()

    def add(
        self,
        sink: str | os.PathLike[str] | TextIO,
        *,
        level: LogLevel | str | None = None,
        format: str | None = None,
        rotation: str | None = None,
        retention: str | int | None = None,
        compression: bool = False,
        serialize: bool = False,
        filter: Callable[[dict[str, Any]], bool] | None = None,
        enqueue: bool = False,
        colorize: bool | None = None,
    ) -> int:
        """Add a handler (file or console sink).

        Args:
            sink: Path to the log file (str or Path object), or sys.stdout/sys.stderr.
            level: Minimum log level for this handler.
            format: Custom format string (e.g., "{time} | {level} | {message}").
            rotation: Rotation strategy ("daily", "hourly", "500 MB", etc.)
                      Only valid for file sinks.
            retention: Retention policy ("10 days" or count as int)
                       Only valid for file sinks.
            compression: Enable gzip compression for rotated files.
                         Only valid for file sinks.
            serialize: Output as JSON instead of text format.
            filter: Optional callable that receives a record dict and returns
                    True if the record should be logged, False to skip.
            enqueue: If True, writes are queued and processed asynchronously
                     in a background thread (thread-safe).
                     If False (default), writes are synchronous (reliable).
                     Only valid for file sinks.
            colorize: Enable ANSI color codes (for console sinks).
                      If None, auto-detect based on whether sink is a TTY.
                      Only valid for console sinks.

        Returns:
            Handler ID for later removal.

        Examples:
            >>> logger.add("app.log")
            >>> logger.add(Path("debug.log"), level="DEBUG")
            >>> logger.add("app.log", rotation="500 MB", retention="10 days")
            >>> logger.add("app.json", serialize=True)
            >>> logger.add("async.log", enqueue=True)  # Async writes
            >>> logger.add(sys.stdout, colorize=True)  # Colored console output
            >>> logger.add(sys.stderr, serialize=True)  # JSON to stderr
        """
        import sys

        if sink is sys.stdout or sink is sys.stderr:
            stream_name = "stdout" if sink is sys.stdout else "stderr"
            resolved_level = _to_log_level(level) if level is not None else None
            resolved_colorize = colorize
            if resolved_colorize is None:
                resolved_colorize = sink.isatty() if hasattr(sink, "isatty") else True

            return self._inner.add_console(
                stream=stream_name,
                level=resolved_level,
                format=format,
                serialize=serialize,
                filter=filter,
                colorize=resolved_colorize,
            )

        sink_str = os.fspath(sink)

        resolved_level = _to_log_level(level) if level is not None else None

        retention_str = None
        if retention is not None:
            retention_str = str(retention) if isinstance(retention, int) else retention

        return self._inner.add(
            sink_str,
            level=resolved_level,
            format=format,
            rotation=rotation,
            retention=retention_str,
            compression=compression,
            serialize=serialize,
            filter=filter,
            enqueue=enqueue,
        )

    def remove(self, handler_id: int | None = None) -> bool:
        """Remove a handler by ID, or all handlers if None.

        Args:
            handler_id: Handler ID to remove, or None to remove all.

        Returns:
            True if handler was removed, False otherwise.

        Examples:
            >>> handler_id = logger.add("app.log")
            >>> logger.remove(handler_id)  # Remove specific handler
            >>> logger.remove()  # Remove ALL handlers (including console)
        """
        return self._inner.remove(handler_id)

    def bind(self, **kwargs: Any) -> Logger:
        """Create a new logger with bound context values.

        Args:
            **kwargs: Key-value pairs to bind to log records.

        Returns:
            A new Logger instance with the bound context.

        Examples:
            >>> user_logger = logger.bind(user_id="123", session="abc")
            >>> user_logger.info("User action")
            # Output includes extra context in JSON mode
        """
        new_inner = self._inner.bind(kwargs)
        return Logger(new_inner, patchers=self._patchers.copy())

    @contextmanager
    def contextualize(self, **kwargs: Any) -> Generator[Logger, None, None]:
        """Temporarily bind context values within a with block.

        Args:
            **kwargs: Key-value pairs to bind temporarily.

        Yields:
            The logger with temporary context.

        Examples:
            >>> with logger.contextualize(request_id="abc"):
            ...     logger.info("Processing")  # includes request_id
            >>> logger.info("Done")  # no request_id
        """
        bound = self.bind(**kwargs)
        original = self._inner
        self._inner = bound._inner
        try:
            yield self
        finally:
            self._inner = original

    def catch(
        self,
        exception: type[BaseException] | tuple[type[BaseException], ...] = Exception,
        *,
        level: str = "ERROR",
        reraise: bool = False,
        message: str = "An error occurred",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to catch and log exceptions.

        Args:
            exception: Exception type(s) to catch.
            level: Log level for the error message.
            reraise: Whether to re-raise the exception after logging.
            message: Custom message prefix.

        Returns:
            Decorator function.

        Examples:
            >>> @logger.catch(ValueError, level="WARNING")
            ... def risky_function():
            ...     raise ValueError("Something went wrong")
            >>> risky_function()  # Logs the exception, doesn't re-raise

            >>> @logger.catch(reraise=True)
            ... def another_function():
            ...     raise RuntimeError("Critical error")
            >>> another_function()  # Logs and re-raises
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(func)
            def wrapper(*args: Any, **func_kwargs: Any) -> Any:
                try:
                    return func(*args, **func_kwargs)
                except exception as e:
                    tb = traceback.format_exc()
                    log_method = getattr(self, level.lower())
                    # _depth=1 to skip this wrapper and show caller of decorated function
                    log_method(f"{message}: {e}", exception=tb, _depth=1)
                    if reraise:
                        raise

            return wrapper

        return decorator

    def add_callback(
        self, callback: Callable[[dict[str, Any]], None], level: LogLevel | str | None = None
    ) -> int:
        """Add a callback to receive log records.

        Args:
            callback: Function to call with log record dict.
            level: Minimum log level for callback invocation.

        Returns:
            Callback ID for later removal.

        Examples:
            >>> def my_callback(record):
            ...     print(f"Got log: {record['message']}")
            >>> callback_id = logger.add_callback(my_callback)
            >>> logger.info("Hello")  # Triggers callback
            >>> logger.remove_callback(callback_id)
        """
        resolved_level = _to_log_level(level) if level is not None else None
        return self._inner.add_callback(callback, resolved_level)

    def remove_callback(self, callback_id: int) -> bool:
        """Remove a callback by ID.

        Args:
            callback_id: Callback ID to remove.

        Returns:
            True if callback was removed, False otherwise.
        """
        return self._inner.remove_callback(callback_id)

    def patch(self, patcher: Callable[[dict[str, Any]], None]) -> Logger:
        """Create a new logger with a patcher function.

        The patcher function is called with the log record dict before
        it is sent to handlers. This allows dynamic modification of
        log records.

        Args:
            patcher: Function that modifies the record dict in-place.

        Returns:
            A new Logger instance with the patcher added.

        Examples:
            >>> def add_request_id(record):
            ...     record["extra"]["request_id"] = get_current_request_id()
            ...
            >>> patched_logger = logger.patch(add_request_id)
            >>> patched_logger.info("Request processed")
            # Record now includes request_id in extra

            >>> # Chain multiple patchers
            >>> logger.patch(add_user_id).patch(add_request_id).info("Log")
        """
        new_patchers = self._patchers.copy()
        new_patchers.append(patcher)
        return Logger(self._inner, patchers=new_patchers)

    def configure(
        self,
        *,
        handlers: list[dict[str, Any]] | None = None,
        levels: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
        patcher: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[int]:
        """Configure the logger from dictionaries.

        Args:
            handlers: List of handler configurations. Each dict can have:
                - sink (required): File path or sys.stdout/sys.stderr
                - level: Minimum log level
                - format: Format string
                - rotation: Rotation strategy (file sinks only)
                - retention: Retention policy (file sinks only)
                - compression: Enable compression (file sinks only)
                - serialize: Output as JSON
                - filter: Filter function
                - enqueue: Async writes (file sinks only, default False)
                - colorize: Enable ANSI colors (console sinks only)
            levels: List of custom level configurations. Each dict must have:
                - name (required): Level name
                - no (required): Numeric value
                - color: Color name
                - icon: Icon symbol
            extra: Default extra fields to bind
            patcher: Default patcher function

        Returns:
            List of handler IDs that were created.

        Examples:
            >>> logger.configure(
            ...     handlers=[
            ...         {"sink": "app.log", "level": "INFO"},
            ...         {"sink": "debug.log", "level": "DEBUG", "rotation": "1 day"},
            ...         {"sink": sys.stdout, "colorize": True},
            ...         {"sink": sys.stderr, "serialize": True},
            ...     ],
            ...     levels=[{"name": "NOTICE", "no": 25, "color": "cyan"}],
            ...     extra={"app": "myapp"},
            ... )
        """
        handler_ids: list[int] = []

        if levels:
            for level_config in levels:
                name = level_config.get("name")
                no = level_config.get("no")
                if name and no is not None:
                    self.level(
                        name,
                        no=no,
                        color=level_config.get("color"),
                        icon=level_config.get("icon"),
                    )

        if handlers:
            for handler_config in handlers:
                sink = handler_config.get("sink")
                if sink:
                    handler_id = self.add(
                        sink,
                        level=handler_config.get("level"),
                        format=handler_config.get("format"),
                        rotation=handler_config.get("rotation"),
                        retention=handler_config.get("retention"),
                        compression=handler_config.get("compression", False),
                        serialize=handler_config.get("serialize", False),
                        filter=handler_config.get("filter"),
                        enqueue=handler_config.get("enqueue", False),
                        colorize=handler_config.get("colorize"),
                    )
                    handler_ids.append(handler_id)

        if extra:
            new_inner = self._inner.bind(extra)
            self._inner = new_inner

        if patcher:
            self._patchers.append(patcher)

        return handler_ids

    def opt(
        self,
        *,
        lazy: bool = False,
        exception: bool = False,
        depth: int = 0,
        backtrace: bool = False,
        diagnose: bool = False,
    ) -> OptLogger:
        """Return a logger with per-message options.

        Args:
            lazy: Defer callable argument evaluation until message is emitted.
                  Useful for expensive computations that should only run if
                  the log level is enabled.
            exception: Auto-capture current exception traceback.
            depth: Stack frame adjustment (reserved for future use).
            backtrace: Extend trace beyond catch point to show full call stack.
            diagnose: Show variable values at each stack frame.

        Returns:
            An OptLogger wrapper with the specified options.

        Examples:
            >>> # Lazy evaluation - expensive_func only called if DEBUG enabled
            >>> logger.opt(lazy=True).debug("Result: {}", expensive_func)

            >>> # Auto-capture exception in except block
            >>> try:
            ...     risky()
            ... except:
            ...     logger.opt(exception=True).error("Failed")

            >>> # Enhanced exception with variable values
            >>> try:
            ...     a = 10
            ...     b = 0
            ...     result = a / b
            ... except:
            ...     logger.opt(diagnose=True).error("Division failed")
            ...     # Shows: a = 10, b = 0
        """
        from ._opt import OptLogger

        return OptLogger(
            self,
            lazy=lazy,
            exception=exception,
            depth=depth,
            backtrace=backtrace,
            diagnose=diagnose,
        )
