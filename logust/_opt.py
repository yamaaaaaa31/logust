"""OptLogger - Logger wrapper with per-message options."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._logger import _LEVEL_VALUES
from ._traceback import capture_exception, current_exc_info

if TYPE_CHECKING:
    from ._logger import Logger
    from ._logust import LogLevel


class OptLogger:
    """Wrapper logger with per-message options.

    Created via Logger.opt(). Provides the same logging methods as Logger
    but with additional behavior based on the options passed to opt().
    """

    def __init__(
        self,
        logger: Logger,
        *,
        lazy: bool = False,
        exception: bool = False,
        depth: int = 0,
        backtrace: bool = False,
        diagnose: bool = False,
        colors: bool | None = None,
        capture: bool = True,
    ) -> None:
        if colors is False:
            # Same handlers and state, with message markup kept as plain text
            logger = logger._with_inner(logger._inner.with_colors(False))
        self._logger = logger
        self._lazy = lazy
        self._exception = exception
        self._depth = depth
        self._backtrace = backtrace
        self._diagnose = diagnose
        self._capture = capture
        # Any of these options means the current exception is captured per call
        self._auto_exception = exception or backtrace or diagnose

    def _resolve_args(self, args: tuple[Any, ...]) -> tuple[Any, ...]:
        """Evaluate callable positional args when ``lazy=True``."""
        if self._lazy and args:
            return tuple([arg() if callable(arg) else arg for arg in args])
        return args

    def _get_exception(self) -> str | None:
        """Get exception traceback with optional enhancements."""
        if self._auto_exception:
            exc_info = current_exc_info()
            if exc_info is not None:
                return capture_exception(
                    self._logger._inner,
                    exc_info,
                    backtrace=self._backtrace,
                    diagnose=self._diagnose,
                )
        return None

    def _uncaptured(
        self, message: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        """``capture=False``: format with the kwargs instead of adding them to extra."""
        if self._capture or not kwargs:
            return message, args, kwargs
        message_str = message if isinstance(message, str) else str(message)
        return message_str.format(*args, **kwargs), (), {}

    def _log(self, level: str, message: str, *args: Any, **kwargs: Any) -> None:
        """Internal log method with option processing."""
        logger = self._logger
        # ``level`` is a built-in method name here, so this equals
        # ``logger.is_level_enabled(level)`` without the enum round trip.
        level_enabled = _LEVEL_VALUES[level] >= logger._inner.min_level
        # For lazy evaluation, skip formatting if level is not enabled
        if self._lazy:
            if not level_enabled:
                return
            # Skip lazy args for disabled modules (user frame: +1 public method, + depth)
            activation = logger._activation
            if activation.rules and activation.caller_disabled(self._depth + 2):
                return
            args = self._resolve_args(args)

        exc = kwargs.pop("exception", None)
        if not exc:
            exc = self._get_exception() if self._auto_exception else None
        if not self._capture:
            if not level_enabled:
                return
            message, args, kwargs = self._uncaptured(message, args, kwargs)
        # Formatting (args + kwargs) happens once in Logger, matching loguru.
        # Add depth: +1 for this method, +1 for the caller (trace/debug/etc), + user's depth
        getattr(logger, level)(
            message,
            *args,
            exception=exc,
            _depth=self._depth + 2,
            **kwargs,
        )

    def trace(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Output TRACE level log message with options."""
        self._log("trace", message, *args, **kwargs)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Output DEBUG level log message with options."""
        self._log("debug", message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Output INFO level log message with options."""
        self._log("info", message, *args, **kwargs)

    def success(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Output SUCCESS level log message with options."""
        self._log("success", message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Output WARNING level log message with options."""
        self._log("warning", message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Output ERROR level log message with options."""
        self._log("error", message, *args, **kwargs)

    def fail(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Output FAIL level log message with options."""
        self._log("fail", message, *args, **kwargs)

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Output CRITICAL level log message with options."""
        self._log("critical", message, *args, **kwargs)

    def log(self, level: str | int | LogLevel, message: str, *args: Any, **kwargs: Any) -> None:
        """Output log message at any level (built-in or custom) with options.

        Args:
            level: Level name (str), numeric value (int) or ``LogLevel``.
            message: Log message with optional format placeholders.
            *args: Format arguments (evaluated lazily if opt(lazy=True)).
            **kwargs: Additional arguments.

        Examples:
            >>> logger.opt(lazy=True).log("NOTICE", "Result: {}", expensive_func)
        """
        if self._lazy:
            logger = self._logger
            # Skip lazy args for a filtered-out level or a disabled module, like
            # the level methods do (user frame: +1 for this method, + depth)
            emit_no = logger._inner.try_resolve_emit_level_no(level)
            if emit_no is not None and emit_no < logger._inner.min_level:
                return
            activation = logger._activation
            if activation.rules and activation.caller_disabled(self._depth + 1):
                return
        exc = kwargs.pop("exception", None) or self._get_exception()
        args = self._resolve_args(args)
        message, args, kwargs = self._uncaptured(message, args, kwargs)
        # Add depth: +1 for this method, + user's depth
        self._logger.log(
            level,
            message,
            *args,
            exception=exc,
            _depth=self._depth + 1,
            **kwargs,
        )
