"""OptLogger - Logger wrapper with per-message options."""

from __future__ import annotations

import sys
import traceback
from typing import TYPE_CHECKING, Any

from ._traceback import format_enhanced_traceback

if TYPE_CHECKING:
    from ._logger import Logger


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
    ) -> None:
        self._logger = logger
        self._lazy = lazy
        self._exception = exception
        self._depth = depth
        self._backtrace = backtrace
        self._diagnose = diagnose

    def _format_message(self, message: str, *args: Any) -> str:
        """Format message, evaluating lazy callables if enabled."""
        if not args:
            return message

        if self._lazy:
            evaluated_args = tuple(arg() if callable(arg) else arg for arg in args)
            return message.format(*evaluated_args)
        return message.format(*args)

    def _get_exception(self) -> str | None:
        """Get exception traceback with optional enhancements."""
        if self._exception or self._backtrace or self._diagnose:
            if sys.exc_info()[0] is not None:
                if self._backtrace or self._diagnose:
                    return format_enhanced_traceback(
                        backtrace=self._backtrace,
                        diagnose=self._diagnose,
                    )
                return traceback.format_exc()
        return None

    def _log(self, level: str, message: str, *args: Any, **kwargs: Any) -> None:
        """Internal log method with option processing."""
        # For lazy evaluation, skip formatting if level is not enabled
        if self._lazy and not self._logger.is_level_enabled(level):
            return

        formatted = self._format_message(message, *args)
        exc = kwargs.pop("exception", None) or self._get_exception()
        log_method = getattr(self._logger, level)
        # Add depth: +1 for this method, +1 for the caller (trace/debug/etc), + user's depth
        log_method(formatted, exception=exc, _depth=self._depth + 2, **kwargs)

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

    def log(self, level: str | int, message: str, *args: Any, **kwargs: Any) -> None:
        """Output log message at any level (built-in or custom) with options.

        Args:
            level: Level name (str) or numeric value (int).
            message: Log message with optional format placeholders.
            *args: Format arguments (evaluated lazily if opt(lazy=True)).
            **kwargs: Additional arguments.

        Examples:
            >>> logger.opt(lazy=True).log("NOTICE", "Result: {}", expensive_func)
        """
        # For lazy evaluation with custom levels, we can't easily check
        # the level in advance, so we format and delegate to the logger
        formatted = self._format_message(message, *args)
        exc = kwargs.pop("exception", None) or self._get_exception()
        # Add depth: +1 for this method, + user's depth
        self._logger.log(level, formatted, exception=exc, _depth=self._depth + 1, **kwargs)
