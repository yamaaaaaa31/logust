"""Logger class - main logging interface."""

from __future__ import annotations

import functools
import os
import re
import sys
import threading
import traceback
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TextIO

from ._logust import LogLevel, PyLogger
from ._template import CALLER_TOKENS, KNOWN_TOKENS, ParsedCallableTemplate


@dataclass(frozen=True, slots=True)
class CallerInfo:
    """Fixed caller information for log records.

    Used with CollectOptions to provide static caller info instead of
    dynamically collecting it from the call stack.
    """

    name: str = ""
    function: str = ""
    line: int = 0
    file: str = ""


@dataclass(frozen=True, slots=True)
class ThreadInfo:
    """Fixed thread information for log records.

    Used with CollectOptions to provide static thread info instead of
    dynamically collecting it.
    """

    name: str = ""
    id: int = 0


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    """Fixed process information for log records.

    Used with CollectOptions to provide static process info instead of
    dynamically collecting it.
    """

    name: str = ""
    id: int = 0


@dataclass(frozen=True, slots=True)
class CollectOptions:
    """Options for controlling information collection per handler.

    Each field can be:
    - None: Auto-detect from format string (default)
    - False: Never collect this info (use empty defaults)
    - True: Always collect this info
    - CallerInfo/ThreadInfo/ProcessInfo: Use fixed values
    """

    caller: bool | CallerInfo | None = None
    thread: bool | ThreadInfo | None = None
    process: bool | ProcessInfo | None = None


# Token pattern for format analysis (matches known tokens only)
# Built from KNOWN_TOKENS to ensure consistency with ParsedCallableTemplate
_FORMAT_TOKEN_PATTERN = re.compile(
    r"\{(" + "|".join(re.escape(t) for t in KNOWN_TOKENS) + r"|extra\[[^\]]+\])(?::[^}]+)?\}"
)


def _collect_options_from_format(format_str: str) -> CollectOptions:
    """Compute CollectOptions from a format string.

    Analyzes which tokens are used in the format to determine
    what information needs to be collected. This is used for
    callable sinks to avoid relying on Rust's needs_* which
    is polluted by callback registration.

    Args:
        format_str: Format template string.

    Returns:
        CollectOptions with explicit True/False values based on format needs.
    """
    used_tokens: set[str] = set()
    for match in _FORMAT_TOKEN_PATTERN.finditer(format_str):
        key = match.group(1)
        if key.startswith("extra["):
            key = "extra"
        used_tokens.add(key)

    needs_caller = bool(used_tokens & CALLER_TOKENS)
    needs_thread = "thread" in used_tokens
    needs_process = "process" in used_tokens

    return CollectOptions(
        caller=needs_caller,
        thread=needs_thread,
        process=needs_process,
    )


if TYPE_CHECKING:
    from ._opt import OptLogger

# Cached process info (invalidated on fork by checking PID)
_CACHED_PROCESS_INFO: tuple[str, int] | None = None
_CACHED_PROCESS_PID: int | None = None


def _get_caller_info(depth: int = 1) -> tuple[str, str, int, str]:
    """Get caller information (module name, function name, line number, file basename).

    Args:
        depth: Number of frames to go back from the caller of this function

    Returns:
        Tuple of (module_name, function_name, line_number, file_basename)
    """
    try:
        frame = sys._getframe(depth + 1)  # +1 to skip this function itself
        code = frame.f_code
        # Get module name from globals, or use filename as fallback
        module_name = frame.f_globals.get("__name__", code.co_filename)
        # Get file basename (not full path)
        file_basename = os.path.basename(code.co_filename)
        return (module_name, code.co_name, frame.f_lineno, file_basename)
    except (ValueError, AttributeError):
        return ("", "", 0, "")


def _get_thread_info() -> tuple[str, int]:
    """Get current thread name and ID.

    Returns:
        Tuple of (thread_name, thread_id)
    """
    thread = threading.current_thread()
    return (thread.name, thread.ident or 0)


def _get_process_info() -> tuple[str, int]:
    """Get current process name and ID.

    Caches the result, but invalidates cache after fork (detected by PID change).

    Returns:
        Tuple of (process_name, process_id)
    """
    global _CACHED_PROCESS_INFO, _CACHED_PROCESS_PID
    current_pid = os.getpid()

    # Invalidate cache if PID changed (fork occurred)
    if _CACHED_PROCESS_INFO is not None and _CACHED_PROCESS_PID == current_pid:
        return _CACHED_PROCESS_INFO

    try:
        import multiprocessing

        name = multiprocessing.current_process().name
    except Exception:
        name = "MainProcess"
    _CACHED_PROCESS_INFO = (name, current_pid)
    _CACHED_PROCESS_PID = current_pid
    return _CACHED_PROCESS_INFO


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
        collect_options: dict[int, CollectOptions] | None = None,
        callback_ids: set[int] | None = None,
        filter_ids: set[int] | None = None,
        raw_callback_ids: set[int] | None = None,
        requirements_cache_box: (
            list[tuple[bool | CallerInfo, bool | ThreadInfo, bool | ProcessInfo] | None] | None
        ) = None,
        aggregated_options_box: (
            list[
                tuple[
                    bool,
                    CallerInfo | None,
                    bool,
                    bool,
                    bool,
                    ThreadInfo | None,
                    bool,
                    bool,
                    bool,
                    ProcessInfo | None,
                    bool,
                    bool,
                    bool,
                    int,
                ]
                | None
            ]
            | None
        ) = None,
    ) -> None:
        self._inner = inner
        self._patchers = patchers if patchers is not None else []
        # Handler ID -> CollectOptions mapping (shared between bound loggers)
        # Use explicit None check to preserve empty containers (empty dict/set are falsy)
        self._collect_options: dict[int, CollectOptions] = (
            collect_options if collect_options is not None else {}
        )
        # Track callable sink IDs for proper removal via remove()
        self._callback_ids: set[int] = callback_ids if callback_ids is not None else set()
        # Track handlers with Rust-side filters to force full record collection
        self._filter_ids: set[int] = filter_ids if filter_ids is not None else set()
        # Track raw callbacks (via add_callback) that need full records
        self._raw_callback_ids: set[int] = (
            raw_callback_ids if raw_callback_ids is not None else set()
        )
        # Cached requirements in a box (list) for sharing between bound loggers
        # Box[0] is the cached value or None if invalid
        self._requirements_cache_box: list[
            tuple[bool | CallerInfo, bool | ThreadInfo, bool | ProcessInfo] | None
        ] = requirements_cache_box if requirements_cache_box is not None else [None]
        # Cached aggregated options in a box for O(1) access during log
        # Format: (caller_true, caller_fixed, caller_none, caller_false,
        #          thread_true, thread_fixed, thread_none, thread_false,
        #          process_true, process_fixed, process_none, process_false,
        #          needs_full_records, tracked_handler_count)
        self._aggregated_options_box: list[
            tuple[
                bool,
                CallerInfo | None,
                bool,
                bool,
                bool,
                ThreadInfo | None,
                bool,
                bool,
                bool,
                ProcessInfo | None,
                bool,
                bool,
                bool,
                int,
            ]
            | None
        ] = aggregated_options_box if aggregated_options_box is not None else [None]

    def _invalidate_requirements_cache(self) -> None:
        """Invalidate all caches (call when handlers change)."""
        self._requirements_cache_box[0] = None
        self._aggregated_options_box[0] = None

    def _get_aggregated_options(
        self,
    ) -> tuple[
        bool,
        CallerInfo | None,
        bool,
        bool,
        bool,
        ThreadInfo | None,
        bool,
        bool,
        bool,
        ProcessInfo | None,
        bool,
        bool,
        bool,
        int,
    ]:
        """Get aggregated CollectOptions, computing and caching if needed.

        Returns cached result or computes from _collect_options.
        This is O(n) on first call after invalidation, O(1) thereafter.
        """
        cached = self._aggregated_options_box[0]
        if cached is not None:
            return cached

        caller_true = False
        caller_fixed: CallerInfo | None = None
        caller_none = False
        caller_false = False

        thread_true = False
        thread_fixed: ThreadInfo | None = None
        thread_none = False
        thread_false = False

        process_true = False
        process_fixed: ProcessInfo | None = None
        process_none = False
        process_false = False

        tracked_handler_count = 0

        for handler_id, opts in self._collect_options.items():
            # Count tracked file handlers (not callbacks)
            if handler_id not in self._callback_ids:
                tracked_handler_count += 1

            if opts.caller is True:
                caller_true = True
            elif isinstance(opts.caller, CallerInfo):
                if caller_fixed is None:
                    caller_fixed = opts.caller
            elif opts.caller is None:
                caller_none = True
            elif opts.caller is False:
                caller_false = True

            if opts.thread is True:
                thread_true = True
            elif isinstance(opts.thread, ThreadInfo):
                if thread_fixed is None:
                    thread_fixed = opts.thread
            elif opts.thread is None:
                thread_none = True
            elif opts.thread is False:
                thread_false = True

            if opts.process is True:
                process_true = True
            elif isinstance(opts.process, ProcessInfo):
                if process_fixed is None:
                    process_fixed = opts.process
            elif opts.process is None:
                process_none = True
            elif opts.process is False:
                process_false = True

        needs_full_records = len(self._raw_callback_ids) > 0 or len(self._filter_ids) > 0

        result = (
            caller_true,
            caller_fixed,
            caller_none,
            caller_false,
            thread_true,
            thread_fixed,
            thread_none,
            thread_false,
            process_true,
            process_fixed,
            process_none,
            process_false,
            needs_full_records,
            tracked_handler_count,
        )
        self._aggregated_options_box[0] = result
        return result

    def _compute_effective_requirements(
        self,
    ) -> tuple[bool | CallerInfo, bool | ThreadInfo, bool | ProcessInfo]:
        """Compute effective requirements considering CollectOptions.

        Results are cached and returned on subsequent calls until invalidated.
        Uses pre-aggregated options for O(1) computation after first call.

        Priority order (highest to lowest):
        1. True - explicit request to collect dynamically
        2. Rust needs - callbacks/filters/format require the data
        3. Fixed value - use fixed value when no dynamic need
        4. False/else - don't collect

        Key principle: If Rust needs the data (callbacks always need full records,
        or format requires it), we MUST collect regardless of caller=False.
        The caller=False setting means "I don't need it for my output", not
        "prevent collection for the entire system".

        Returns:
            Tuple of (caller_requirement, thread_requirement, process_requirement)
            where each is True (collect), False (skip), or a fixed value instance.
        """
        # Return cached result if available (O(1) hot path)
        cached = self._requirements_cache_box[0]
        if cached is not None:
            return cached

        if not self._collect_options:
            # No CollectOptions, use Rust-detected requirements
            result: tuple[bool | CallerInfo, bool | ThreadInfo, bool | ProcessInfo] = (
                self._inner.needs_caller_info,
                self._inner.needs_thread_info,
                self._inner.needs_process_info,
            )
            self._requirements_cache_box[0] = result
            return result

        # Get pre-aggregated options (O(1) if already cached)
        (
            caller_true,
            caller_fixed,
            caller_none,
            caller_false,
            thread_true,
            thread_fixed,
            thread_none,
            thread_false,
            process_true,
            process_fixed,
            process_none,
            process_false,
            needs_full_records,
            tracked_handler_count,
        ) = self._get_aggregated_options()

        # Check if there are untracked handlers (O(1) - uses cached tracked_handler_count)
        has_untracked_handlers = self._inner.handler_count > tracked_handler_count

        # If there are untracked handlers (like default console) and they need info, collect.
        has_untracked_caller_need = (
            has_untracked_handlers and self._inner.needs_caller_info_for_handlers
        )
        has_untracked_thread_need = (
            has_untracked_handlers and self._inner.needs_thread_info_for_handlers
        )
        has_untracked_process_need = (
            has_untracked_handlers and self._inner.needs_process_info_for_handlers
        )

        # Dynamic collection is needed when:
        # 1. Auto-detect (xxx_none) and handler format needs it
        # 2. Raw callbacks/filters need full records
        # 3. Untracked handlers may need it
        needs_dynamic_caller = (
            (self._inner.needs_caller_info_for_handlers and caller_none)
            or needs_full_records
            or has_untracked_caller_need
        )
        needs_dynamic_thread = (
            (self._inner.needs_thread_info_for_handlers and thread_none)
            or needs_full_records
            or has_untracked_thread_need
        )
        needs_dynamic_process = (
            (self._inner.needs_process_info_for_handlers and process_none)
            or needs_full_records
            or has_untracked_process_need
        )

        # Caller
        if caller_true:
            needs_caller: bool | CallerInfo = True
        elif needs_dynamic_caller:
            needs_caller = True
        elif caller_fixed is not None:
            needs_caller = caller_fixed
        elif caller_false:
            needs_caller = False
        else:
            needs_caller = False

        # Thread
        if thread_true:
            needs_thread: bool | ThreadInfo = True
        elif needs_dynamic_thread:
            needs_thread = True
        elif thread_fixed is not None:
            needs_thread = thread_fixed
        elif thread_false:
            needs_thread = False
        else:
            needs_thread = False

        # Process
        if process_true:
            needs_process: bool | ProcessInfo = True
        elif needs_dynamic_process:
            needs_process = True
        elif process_fixed is not None:
            needs_process = process_fixed
        elif process_false:
            needs_process = False
        else:
            needs_process = False

        # Cache and return the result
        result = (needs_caller, needs_thread, needs_process)
        self._requirements_cache_box[0] = result
        return result

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

        # Compute effective requirements considering CollectOptions
        needs_caller, needs_thread, needs_process = self._compute_effective_requirements()

        if needs_caller is False and needs_thread is False and needs_process is False:
            if exception is None:
                getattr(self._inner, level_name)(str(message))
            else:
                getattr(self._inner, level_name)(str(message), exception=exception)
            return

        if needs_thread is False and needs_process is False:
            if needs_caller is True:
                name, function, line, file = _get_caller_info(depth + 1)
            else:
                # needs_caller is CallerInfo (False case already returned above)
                name, function, line, file = (
                    needs_caller.name,  # type: ignore[union-attr]
                    needs_caller.function,  # type: ignore[union-attr]
                    needs_caller.line,  # type: ignore[union-attr]
                    needs_caller.file,  # type: ignore[union-attr]
                )
            if exception is None:
                getattr(self._inner, level_name)(
                    str(message), name=name, function=function, line=line, file=file
                )
            else:
                getattr(self._inner, level_name)(
                    str(message),
                    exception=exception,
                    name=name,
                    function=function,
                    line=line,
                    file=file,
                )
            return

        # Handle caller info
        c_name: str | None
        c_function: str | None
        c_line: int | None
        c_file: str | None
        if needs_caller is True:
            c_name, c_function, c_line, c_file = _get_caller_info(depth + 1)
        elif needs_caller is not False:
            c_name, c_function, c_line, c_file = (
                needs_caller.name,
                needs_caller.function,
                needs_caller.line,
                needs_caller.file,
            )
        else:
            c_name, c_function, c_line, c_file = None, None, None, None

        # Handle thread info
        t_name: str | None
        t_id: int | None
        if needs_thread is True:
            t_name, t_id = _get_thread_info()
        elif needs_thread is not False:
            t_name = needs_thread.name
            t_id = needs_thread.id
        else:
            t_name, t_id = None, None

        # Handle process info
        p_name: str | None
        p_id: int | None
        if needs_process is True:
            p_name, p_id = _get_process_info()
        elif needs_process is not False:
            p_name = needs_process.name
            p_id = needs_process.id
        else:
            p_name, p_id = None, None

        if exception is None:
            getattr(self._inner, level_name)(
                str(message),
                name=c_name,
                function=c_function,
                line=c_line,
                file=c_file,
                thread_name=t_name,
                thread_id=t_id,
                process_name=p_name,
                process_id=p_id,
            )
        else:
            getattr(self._inner, level_name)(
                str(message),
                exception=exception,
                name=c_name,
                function=c_function,
                line=c_line,
                file=c_file,
                thread_name=t_name,
                thread_id=t_id,
                process_name=p_name,
                process_id=p_id,
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
            self._log_with_level(level, _LEVEL_VALUE_MAP[level], message, exception, _depth + 1)
            return

        # Compute effective requirements considering CollectOptions
        needs_caller, needs_thread, needs_process = self._compute_effective_requirements()

        if needs_caller is False and needs_thread is False and needs_process is False:
            if exception is None:
                self._inner.log(level, str(message))
            else:
                self._inner.log(level, str(message), exception=exception)
            return

        if needs_thread is False and needs_process is False:
            if needs_caller is True:
                name, function, line, file = _get_caller_info(_depth + 1)
            else:
                # needs_caller is CallerInfo (False case already returned above)
                name, function, line, file = (
                    needs_caller.name,  # type: ignore[union-attr]
                    needs_caller.function,  # type: ignore[union-attr]
                    needs_caller.line,  # type: ignore[union-attr]
                    needs_caller.file,  # type: ignore[union-attr]
                )
            if exception is None:
                self._inner.log(
                    level, str(message), name=name, function=function, line=line, file=file
                )
            else:
                self._inner.log(
                    level,
                    str(message),
                    exception=exception,
                    name=name,
                    function=function,
                    line=line,
                    file=file,
                )
            return

        name_: str | None
        function_: str | None
        line_: int | None
        file_: str | None
        if needs_caller is True:
            name_, function_, line_, file_ = _get_caller_info(_depth + 1)
        elif needs_caller is not False:
            name_, function_, line_, file_ = (
                needs_caller.name,
                needs_caller.function,
                needs_caller.line,
                needs_caller.file,
            )
        else:
            name_, function_, line_, file_ = None, None, None, None

        thread_name: str | None
        thread_id: int | None
        if needs_thread is True:
            thread_name, thread_id = _get_thread_info()
        elif needs_thread is not False:
            thread_name = needs_thread.name
            thread_id = needs_thread.id
        else:
            thread_name, thread_id = None, None

        process_name: str | None
        process_id: int | None
        if needs_process is True:
            process_name, process_id = _get_process_info()
        elif needs_process is not False:
            process_name = needs_process.name
            process_id = needs_process.id
        else:
            process_name, process_id = None, None

        if exception is None:
            self._inner.log(
                level,
                str(message),
                name=name_,
                function=function_,
                line=line_,
                file=file_,
                thread_name=thread_name,
                thread_id=thread_id,
                process_name=process_name,
                process_id=process_id,
            )
        else:
            self._inner.log(
                level,
                str(message),
                exception=exception,
                name=name_,
                function=function_,
                line=line_,
                file=file_,
                thread_name=thread_name,
                thread_id=thread_id,
                process_name=process_name,
                process_id=process_id,
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
        sink: str | os.PathLike[str] | TextIO | Callable[[str], Any],
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
        collect: CollectOptions | None = None,
    ) -> int:
        """Add a handler (file, console, or callable sink).

        Args:
            sink: Path to the log file (str or Path object), sys.stdout/sys.stderr,
                  or a callable that receives formatted log messages.
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
            collect: Options for controlling information collection.
                     Can override auto-detection from format string.

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
            >>> logger.add(lambda msg: print(msg))  # Callable sink
            >>> logger.add("app.log", collect=CollectOptions(caller=False))

        Note:
            Callable sinks can be removed with remove() or remove_callback().
        """
        import sys

        # Check for callable sink first (before checking stdout/stderr)
        if callable(sink) and sink not in (sys.stdout, sys.stderr):
            handler_id = self._add_callable_sink(
                sink,
                level=level,
                format=format,
                serialize=serialize,
                filter=filter,
            )
            # For callable sinks, compute CollectOptions from format if not specified
            # This avoids relying on Rust's needs_* which is polluted by callback registration
            if collect is not None:
                resolved_collect = collect
            else:
                default_format = "{time} | {level:<8} | {name}:{function}:{line} - {message}"
                resolved_collect = _collect_options_from_format(format or default_format)
            self._collect_options[handler_id] = resolved_collect
            # Track as callback for proper removal via remove()
            self._callback_ids.add(handler_id)
            # Track handlers with filters (they need full records)
            if filter is not None:
                self._filter_ids.add(handler_id)
            self._invalidate_requirements_cache()
            return handler_id

        if sink is sys.stdout or sink is sys.stderr:
            stream_name = "stdout" if sink is sys.stdout else "stderr"
            resolved_level = _to_log_level(level) if level is not None else None
            resolved_colorize = colorize
            if resolved_colorize is None:
                resolved_colorize = sink.isatty() if hasattr(sink, "isatty") else False

            handler_id = self._inner.add_console(
                stream=stream_name,
                level=resolved_level,
                format=format,
                serialize=serialize,
                filter=filter,
                colorize=resolved_colorize,
            )
            # Always track handler with CollectOptions (default to auto-detect if not specified)
            self._collect_options[handler_id] = collect if collect is not None else CollectOptions()
            if filter is not None:
                self._filter_ids.add(handler_id)
            self._invalidate_requirements_cache()
            return handler_id

        # At this point sink must be a path (str or PathLike), not TextIO
        sink_str = os.fspath(sink)  # type: ignore[arg-type]

        resolved_level = _to_log_level(level) if level is not None else None

        retention_str = None
        if retention is not None:
            retention_str = str(retention) if isinstance(retention, int) else retention

        handler_id = self._inner.add(
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
        # Always track handler with CollectOptions (default to auto-detect if not specified)
        self._collect_options[handler_id] = collect if collect is not None else CollectOptions()
        if filter is not None:
            self._filter_ids.add(handler_id)
        self._invalidate_requirements_cache()
        return handler_id

    def _add_callable_sink(
        self,
        sink: Callable[[str], Any],
        *,
        level: LogLevel | str | None = None,
        format: str | None = None,
        serialize: bool = False,
        filter: Callable[[dict[str, Any]], bool] | None = None,
    ) -> int:
        """Add a callable as a sink (internal method).

        The callable will receive formatted log messages as strings.

        Args:
            sink: Callable that receives formatted log messages.
            level: Minimum log level for this handler.
            format: Custom format string.
            serialize: Output as JSON instead of text format.
            filter: Optional callable that receives a record dict and returns
                    True if the record should be logged, False to skip.

        Returns:
            Handler ID for later removal.
        """
        import json

        resolved_level = _to_log_level(level) if level is not None else None
        default_format = "{time} | {level:<8} | {name}:{function}:{line} - {message}"
        template_str = format or default_format

        # Pre-parse template for efficient single-pass formatting
        parsed_template = ParsedCallableTemplate(template_str)

        def callback_wrapper(record: dict[str, Any]) -> None:
            # Apply filter if provided
            if filter is not None and not filter(record):
                return

            try:
                if serialize:
                    # Output as JSON matching Rust's format_record_json
                    json_record: dict[str, Any] = {
                        "time": record.get("timestamp", ""),
                        "level": record.get("level", ""),
                        "message": record.get("message", ""),
                    }
                    # Only include non-empty caller info
                    if record.get("name"):
                        json_record["name"] = record["name"]
                    if record.get("function"):
                        json_record["function"] = record["function"]
                    if record.get("line"):
                        json_record["line"] = record["line"]
                    # Include extra if non-empty
                    extra = record.get("extra", {})
                    if extra:
                        json_record["extra"] = extra
                    # Include exception if present
                    if record.get("exception"):
                        json_record["exception"] = record["exception"]
                    formatted = json.dumps(json_record)
                else:
                    # Format using pre-parsed template (single-pass, ~1-2us faster)
                    formatted = parsed_template.format(record)

                sink(formatted)
            except Exception:
                # Silently ignore sink errors (like loguru behavior)
                pass

        return self._inner.add_callback(callback_wrapper, resolved_level)

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
        # If this is a callable sink, redirect to remove_callback
        if handler_id is not None and handler_id in self._callback_ids:
            return self.remove_callback(handler_id)

        result = self._inner.remove(handler_id)
        # Clean up CollectOptions and tracking sets
        if handler_id is not None:
            self._collect_options.pop(handler_id, None)
            self._filter_ids.discard(handler_id)
            self._invalidate_requirements_cache()
        else:
            # Remove all handlers: also remove all callable sinks and raw callbacks
            # Use batch removal to avoid O(n²) cache updates
            all_callback_ids = list(self._callback_ids) + list(self._raw_callback_ids)
            callbacks_removed = (
                self._inner.remove_callbacks(all_callback_ids) if all_callback_ids else 0
            )
            self._collect_options.clear()
            self._callback_ids.clear()
            self._filter_ids.clear()
            self._raw_callback_ids.clear()
            self._invalidate_requirements_cache()
            # Return True if handlers OR callbacks were removed
            return result or callbacks_removed > 0
        return result

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
        return Logger(
            new_inner,
            patchers=self._patchers.copy(),
            collect_options=self._collect_options,
            callback_ids=self._callback_ids,
            filter_ids=self._filter_ids,
            raw_callback_ids=self._raw_callback_ids,
            requirements_cache_box=self._requirements_cache_box,
            aggregated_options_box=self._aggregated_options_box,
        )

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
        callback_id = self._inner.add_callback(callback, resolved_level)
        # Track with default CollectOptions (auto-detect) so callbacks get full records
        self._collect_options[callback_id] = CollectOptions()
        # Track as raw callback (receives raw records, needs full records)
        self._raw_callback_ids.add(callback_id)
        self._invalidate_requirements_cache()
        return callback_id

    def remove_callback(self, callback_id: int) -> bool:
        """Remove a callback by ID.

        Args:
            callback_id: Callback ID to remove.

        Returns:
            True if callback was removed, False otherwise.
        """
        result = self._inner.remove_callback(callback_id)
        # Clean up CollectOptions and tracking sets
        self._collect_options.pop(callback_id, None)
        self._callback_ids.discard(callback_id)
        self._filter_ids.discard(callback_id)
        self._raw_callback_ids.discard(callback_id)
        self._invalidate_requirements_cache()
        return result

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
        return Logger(
            self._inner,
            patchers=new_patchers,
            collect_options=self._collect_options,
            callback_ids=self._callback_ids,
            filter_ids=self._filter_ids,
            raw_callback_ids=self._raw_callback_ids,
            requirements_cache_box=self._requirements_cache_box,
            aggregated_options_box=self._aggregated_options_box,
        )

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
