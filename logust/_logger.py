"""Logger class - main logging interface."""

from __future__ import annotations

import builtins
import datetime
import functools
import inspect
import itertools
import os
import re
import string
import sys
import threading
import traceback
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any, TextIO, TypeVar, cast, overload

from ._logust import CONTEXT_VAR, LogLevel, PyLogger, record_time_fields, set_context
from ._parse import parse as _parse_file
from ._record import RecordLevelStr, RecordProcess, RecordThread
from ._template import (
    CALLER_TOKENS,
    KNOWN_TOKENS,
    PROCESS_TOKENS,
    THREAD_TOKENS,
    ParsedCallableTemplate,
)
from ._traceback import capture_exception, current_exc_info
from ._types import Level

_F = TypeVar("_F", bound=Callable[..., Any])

# ``contextualize()`` values of the current thread/task (see ``Logger.contextualize``).
# Created in Rust so ``PyLogger.log_fast`` reads the same variable; ``set_context``
# is its ``set()`` and also tells Rust the variable is in use.
_CONTEXT = CONTEXT_VAR
_set_context = set_context


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
    r"\{(" + "|".join(re.escape(t) for t in KNOWN_TOKENS) + r"|extra\[[^\]]+\])(?::[^}]*)?\}"
)
_FORMATTER = string.Formatter()


def _format_field_root(field_name: str) -> str | None:
    """Return the root kwarg name consumed by a format field."""
    if not field_name:
        return None

    dot_index = field_name.find(".")
    bracket_index = field_name.find("[")
    split_indexes = [index for index in (dot_index, bracket_index) if index != -1]
    root = field_name[: min(split_indexes)] if split_indexes else field_name
    if not root or root.isdigit():
        return None
    return root or None


def _collect_format_roots(format_string: str, consumed: set[str]) -> None:
    """Collect root kwarg names referenced by a format string."""
    for _, field_name, format_spec, _ in _FORMATTER.parse(format_string):
        if field_name is not None:
            root = _format_field_root(field_name)
            if root is not None:
                consumed.add(root)
        if format_spec:
            _collect_format_roots(format_spec, consumed)


def _parse_format_roots(format_string: str) -> frozenset[str]:
    """Root kwarg names referenced by a format string."""
    consumed: set[str] = set()
    _collect_format_roots(format_string, consumed)
    return frozenset(consumed)


# Messages are usually short literals reused on every call. Longer ones (request
# bodies, dumps) are parsed each time so the cache never pins large strings:
# at most _FORMAT_ROOTS_CACHE_SIZE keys of _FORMAT_ROOTS_MAX_LEN characters.
_FORMAT_ROOTS_MAX_LEN = 512
_FORMAT_ROOTS_CACHE_SIZE = 1024
_cached_format_roots = functools.lru_cache(maxsize=_FORMAT_ROOTS_CACHE_SIZE)(_parse_format_roots)


def _split_kwargs_for_format(
    message: Any, kwargs: dict[str, Any], args: tuple[Any, ...] = ()
) -> tuple[str, dict[str, Any]]:
    """Format message with args/kwargs and return kwargs not consumed by placeholders.

    Mirrors loguru: ``message.format(*args, **kwargs)`` is applied only when
    positional or keyword arguments are given. Bad placeholders raise
    ``IndexError`` / ``KeyError`` just like ``str.format``.

    Non-str messages are coerced via ``str()`` to match the no-kwargs path
    (`_log_with_level` already wraps the message with ``str(...)`` before
    passing it to the inner logger).

    Returned per-call extra values are bound like ``bind()`` values and are
    coerced to strings by the inner logger.
    """
    message_str = message if isinstance(message, str) else str(message)
    if not kwargs:
        return message_str.format(*args), {}
    consumed = (
        _cached_format_roots(message_str)
        if len(message_str) <= _FORMAT_ROOTS_MAX_LEN
        else _parse_format_roots(message_str)
    )
    formatted_message = message_str.format(*args, **kwargs)
    extra_kwargs = {key: value for key, value in kwargs.items() if key not in consumed}
    return formatted_message, extra_kwargs


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
    needs_thread = bool(used_tokens & THREAD_TOKENS)
    needs_process = bool(used_tokens & PROCESS_TOKENS)

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
    """Get caller information (module name, function name, line number, file path).

    The file path is the code object's ``co_filename``; Rust derives the basename
    for ``{file}`` / ``{file.name}`` and keeps the path for ``{file.path}``.

    Args:
        depth: Number of frames to go back from the caller of this function

    Returns:
        Tuple of (module_name, function_name, line_number, file_path)
    """
    try:
        frame = sys._getframe(depth + 1)  # +1 to skip this function itself
        code = frame.f_code
        # Get module name from globals, or use filename as fallback
        module_name = frame.f_globals.get("__name__", code.co_filename)
        return (module_name, code.co_name, frame.f_lineno, code.co_filename)
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


# ``record["level"]`` values handed to patchers, keyed by the level name as passed
# to the log call; cleared whenever a level is (re)registered so icon changes are
# picked up.
_PATCH_LEVELS: dict[str, RecordLevelStr] = {}
# ``record["thread"]`` / ``record["process"]`` values handed to patchers, by id
_PATCH_THREADS: dict[int, RecordThread] = {}
_PATCH_PROCESSES: dict[int, RecordProcess] = {}


def _patch_thread_value() -> RecordThread:
    """Cached ``record["thread"]`` for patchers."""
    thread = threading.current_thread()
    ident = thread.ident or 0
    value = _PATCH_THREADS.get(ident)
    if value is None or value.name != thread.name:
        value = RecordThread(ident, thread.name)
        if len(_PATCH_THREADS) > 1024:
            _PATCH_THREADS.clear()
        _PATCH_THREADS[ident] = value
    return value


def _patch_process_value() -> RecordProcess:
    """Cached ``record["process"]`` for patchers."""
    name, pid = _get_process_info()
    value = _PATCH_PROCESSES.get(pid)
    if value is None or value.name != name:
        value = RecordProcess(pid, name)
        _PATCH_PROCESSES.clear()
        _PATCH_PROCESSES[pid] = value
    return value


def _fill_time(record: dict[str, Any]) -> None:
    time, timestamp, elapsed = record_time_fields()
    record.setdefault("time", time)
    record.setdefault("timestamp", timestamp)
    record.setdefault("elapsed", elapsed)


def _fill_thread(record: dict[str, Any]) -> None:
    record.setdefault("thread", _patch_thread_value())


def _fill_process(record: dict[str, Any]) -> None:
    record.setdefault("process", _patch_process_value())


# Lazy patcher-record key -> function that sets it (and its siblings)
_PATCH_LAZY: dict[str, Callable[[dict[str, Any]], None]] = {
    "time": _fill_time,
    "timestamp": _fill_time,
    "elapsed": _fill_time,
    "thread": _fill_thread,
    "process": _fill_process,
}
_NO_PENDING: frozenset[str] = frozenset()


class _PatchRecord(dict[str, Any]):
    """Record dict handed to patchers.

    ``time``, ``timestamp``, ``elapsed``, ``thread`` and ``process`` are computed
    on first access, so patchers that only touch ``record["extra"]`` cost no more
    than before. Whole-dict operations (iteration, ``len``, ``copy``, ``==``,
    ``repr``, ...) compute every pending key first, so the record behaves like a
    plain dict holding all keys.
    """

    # Keys not computed yet; replaced per instance as keys get filled
    _pending: frozenset[str] = frozenset(_PATCH_LAZY)

    def _fill(self, key: str) -> None:
        fill = _PATCH_LAZY[key]
        # Calls dict methods directly: the overrides below would recurse
        pending = self._pending
        done = {k for k, f in _PATCH_LAZY.items() if f is fill}
        self._pending = pending - done
        tmp: dict[str, Any] = {}
        fill(tmp)
        for k, v in tmp.items():
            if k in pending and not dict.__contains__(self, k):
                dict.__setitem__(self, k, v)

    def _fill_all(self) -> None:
        while self._pending:
            self._fill(next(iter(self._pending)))

    def __missing__(self, key: str) -> Any:
        if key in self._pending:
            self._fill(key)
            return dict.__getitem__(self, key)
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        return dict.__contains__(self, key) or key in self._pending

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._pending and not dict.__contains__(self, key):
            self._fill(key)
        return dict.get(self, key, default)

    def __delitem__(self, key: str) -> None:
        self._fill_all()
        dict.__delitem__(self, key)

    def setdefault(self, key: str, default: Any = None) -> Any:
        self._fill_all()
        return dict.setdefault(self, key, default)

    def pop(self, key: str, *default: Any) -> Any:
        self._fill_all()
        return dict.pop(self, key, *default)

    def popitem(self) -> tuple[str, Any]:
        self._fill_all()
        return dict.popitem(self)

    def clear(self) -> None:
        self._pending = _NO_PENDING
        dict.clear(self)

    def keys(self) -> Any:
        self._fill_all()
        return dict.keys(self)

    def values(self) -> Any:
        self._fill_all()
        return dict.values(self)

    def items(self) -> Any:
        self._fill_all()
        return dict.items(self)

    def __iter__(self) -> Any:
        self._fill_all()
        return dict.__iter__(self)

    def __reversed__(self) -> Any:
        self._fill_all()
        return dict.__reversed__(self)

    def __len__(self) -> int:
        self._fill_all()
        return dict.__len__(self)

    def copy(self) -> dict[str, Any]:
        self._fill_all()
        return dict(dict.items(self))

    def __eq__(self, other: object) -> bool:
        self._fill_all()
        if isinstance(other, _PatchRecord):
            other._fill_all()
        return dict.__eq__(self, other)

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    __hash__ = None

    def __or__(self, other: Any) -> Any:
        self._fill_all()
        return dict(dict.items(self)) | other

    def __ror__(self, other: Any) -> Any:
        self._fill_all()
        return other | dict(dict.items(self))

    def __repr__(self) -> str:
        self._fill_all()
        return dict.__repr__(self)

    def __reduce__(self) -> Any:
        self._fill_all()
        return (dict, (dict(dict.items(self)),))


def _to_log_level(level: LogLevel | str) -> LogLevel:
    """Convert string level name to LogLevel enum."""
    if isinstance(level, str):
        return getattr(LogLevel, level.capitalize())  # type: ignore[no-any-return]
    return level


def _check_utf8_encoding(encoding: str) -> None:
    """Accept any alias of UTF-8; file sinks are always written as UTF-8 by Rust."""
    import codecs

    try:
        name = codecs.lookup(encoding).name
    except LookupError:
        raise ValueError(f"Unknown encoding: {encoding!r}") from None
    if name != "utf-8":
        raise ValueError(
            f"Unsupported encoding: {encoding!r}; logust file sinks always write UTF-8"
        )


def _report_sink_error(handler_id: int | None, record: Any) -> None:
    """Print a loguru-style report of the exception being handled to stderr."""
    stderr = sys.stderr
    if stderr is None:
        return
    try:
        try:
            record_repr = str(record)
        except Exception:
            record_repr = "/!\\ Unprintable record /!\\"
        stderr.write(f"--- Logging error in Logust Handler #{handler_id} ---\n")
        stderr.write(f"Record was: {record_repr}\n")
        traceback.print_exc(file=stderr)
        stderr.write("--- End of logging error ---\n")
        flush = getattr(stderr, "flush", None)
        if callable(flush):
            flush()
    except OSError:
        pass


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

# ``u32::MAX`` — matches Rust conservative merge for unknown emit severity.
_EMIT_NO_SUPERSET: int = 4_294_967_295

# Built-in level values in the slot order of Rust's ``LogLevel::slot`` (one nibble
# each in the ``PyLogger.set_fast_collect`` table).
_FAST_LEVELS: tuple[int, ...] = (5, 10, 20, 25, 30, 40, 45, 50)
_FAST_UNAVAILABLE = 8
# Owner ids for the ``fast_collect`` table, one per Logger family (a Logger and
# the loggers derived from it), so two Loggers wrapping one PyLogger never use
# each other's table. 0 is never handed out.
_FAST_OWNERS = itertools.count(1)


def _next_fast_owner() -> int:
    owner = next(_FAST_OWNERS) & 0xFFFF
    return owner or _next_fast_owner()


def _coerce_emit_no_u32(emit_no: int) -> int:
    """Clamp numeric severity to ``0 .. 0xFFFFFFFF`` for Rust ``u32`` APIs."""
    if emit_no < 0:
        return 0
    if emit_no > _EMIT_NO_SUPERSET:
        return _EMIT_NO_SUPERSET
    return emit_no


class _ModuleActivation:
    """Per-module enable/disable rules shared by a logger and its bound children.

    ``rules`` holds ``(dotted_prefix, enabled)`` pairs, most specific first
    (``""`` matches every module). It is empty until a module is disabled, so
    the logging hot path only checks its truthiness. ``cache`` maps a module
    name to its resolved state and is replaced whenever the rules change.
    Writers set ``rules`` before ``cache`` and readers load ``cache`` first,
    so a reader never stores a stale answer in the current cache.
    """

    __slots__ = ("_lock", "cache", "rules")

    def __init__(self) -> None:
        self.rules: tuple[tuple[str, bool], ...] = ()
        self.cache: dict[str, bool] = {}
        self._lock = threading.Lock()

    def change(self, name: str, enabled: bool) -> None:
        """Apply ``enable(name)`` / ``disable(name)`` with loguru's semantics."""
        prefix = name + "." if name else ""
        with self._lock:
            # Rules for ``name`` and its submodules are superseded by this call.
            rules = [(p, s) for p, s in self.rules if not p.startswith(prefix)]
            parent = next((s for p, s in rules if prefix.startswith(p)), True)
            if parent != enabled:
                rules.append((prefix, enabled))
                rules.sort(key=lambda rule: rule[0].count("."), reverse=True)
            self.rules = tuple(rules)
            self.cache = {}

    def has_rule(self, name: str) -> bool:
        """Whether ``enable(name)`` / ``disable(name)`` left a rule for ``name``."""
        prefix = name + "." if name else ""
        return any(rule_prefix == prefix for rule_prefix, _ in self.rules)

    def is_disabled(self, name: str) -> bool:
        """Return True if messages from module ``name`` are disabled."""
        cache = self.cache
        rules = self.rules
        try:
            return not cache[name]
        except KeyError:
            pass
        dotted = name + "."
        enabled = True
        for prefix, status in rules:
            if dotted.startswith(prefix):
                enabled = status
                break
        cache[name] = enabled
        return not enabled

    def caller_disabled(self, depth: int) -> bool:
        """Like ``is_disabled`` for the module ``depth`` frames above the caller.

        Uses the same frame and name as ``_get_caller_info(depth)``.
        """
        try:
            frame = sys._getframe(depth + 1)
        except ValueError:
            return False
        return self.is_disabled(frame.f_globals.get("__name__", frame.f_code.co_filename))


def _rotation_to_str(rotation: str | datetime.timedelta | datetime.time) -> str:
    """Convert a ``rotation`` value into the string form the Rust sink understands.

    Runs once in ``add()``. Only values the Rust side can honor exactly are accepted.
    """
    if isinstance(rotation, str):
        return rotation
    if isinstance(rotation, datetime.timedelta):
        if rotation == datetime.timedelta(days=1):
            return "daily"
        if rotation == datetime.timedelta(hours=1):
            return "hourly"
        raise ValueError(
            f"Unsupported rotation interval {rotation!r}: only timedelta(days=1) "
            "(daily, at midnight) and timedelta(hours=1) (hourly, on the hour) are supported"
        )
    if isinstance(rotation, datetime.time):
        if rotation.tzinfo is None and rotation == datetime.time(0, 0):
            return "daily"
        raise ValueError(
            f"Unsupported rotation time {rotation!r}: only time(0, 0) "
            "(daily, at local midnight) is supported"
        )
    raise TypeError(
        f"rotation must be str, datetime.timedelta or datetime.time, not {type(rotation).__name__}"
    )


def _is_coroutine_callable(obj: Callable[..., Any]) -> bool:
    """Whether calling ``obj`` returns a coroutine (async function or async ``__call__``)."""
    if inspect.iscoroutinefunction(obj):
        return True
    # Instances whose class defines ``async def __call__``
    call = inspect.getattr_static(type(obj), "__call__", None)
    return inspect.iscoroutinefunction(call)


def _level_from_info(info: tuple[str, int, str, str | None]) -> Level:
    name, no, color, icon = info
    return Level(name, no, color, icon or "")


def _exception_str(exc: BaseException) -> str:
    """``str(exc)``, or loguru's placeholder when ``__str__`` itself raises."""
    try:
        return str(exc)
    except Exception:
        return "<exception str() failed>"


class Catcher:
    """Context manager and decorator returned by ``Logger.catch()``.

    Logs exceptions that leave its block (or decorated function) and, unless
    ``reraise`` is set, suppresses them.
    """

    __slots__ = (
        "_default",
        "_exception",
        "_exclude",
        "_from_decorator",
        "_level",
        "_logger",
        "_message",
        "_onerror",
        "_reraise",
    )

    def __init__(
        self,
        logger: Logger,
        exception: type[BaseException] | tuple[type[BaseException], ...],
        exclude: type[BaseException] | tuple[type[BaseException], ...] | None,
        level: str | int,
        reraise: bool,
        onerror: Callable[[BaseException], Any] | None,
        message: str,
        default: Any,
        from_decorator: bool = False,
    ) -> None:
        self._logger = logger
        self._exception = exception
        self._exclude = exclude
        self._level = level
        self._reraise = reraise
        self._onerror = onerror
        self._message = message
        self._default = default
        self._from_decorator = from_decorator

    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if exc_type is None or exc_value is None:
            return False
        if not issubclass(exc_type, self._exception):
            return False
        if self._exclude is not None and issubclass(exc_type, self._exclude):
            return False

        tb_str = capture_exception(self._logger._inner, (exc_type, exc_value, tb))
        # Point the record at the ``with`` block, or at the caller of the decorated function
        depth = 2 if self._from_decorator else 1
        # The exception text is data: never parse it as color markup
        logger = self._logger._with_inner(self._logger._inner.with_colors(False))
        logger.log(
            self._level,
            f"{self._message}: {_exception_str(exc_value)}",
            exception=tb_str,
            _depth=depth,
        )
        if self._onerror is not None:
            self._onerror(exc_value)
        return not self._reraise

    def __call__(self, function: _F) -> _F:
        catcher = Catcher(
            self._logger,
            self._exception,
            self._exclude,
            self._level,
            self._reraise,
            self._onerror,
            self._message,
            self._default,
            from_decorator=True,
        )
        default = self._default

        if inspect.iscoroutinefunction(function):

            @functools.wraps(function)
            async def catch_async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with catcher:
                    return await function(*args, **kwargs)
                return default

            return cast("_F", catch_async_wrapper)

        if inspect.isgeneratorfunction(function):

            @functools.wraps(function)
            def catch_generator_wrapper(*args: Any, **kwargs: Any) -> Any:
                with catcher:
                    return (yield from function(*args, **kwargs))
                return default

            return cast("_F", catch_generator_wrapper)

        @functools.wraps(function)
        def catch_wrapper(*args: Any, **kwargs: Any) -> Any:
            with catcher:
                return function(*args, **kwargs)
            return default

        return cast("_F", catch_wrapper)


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
        context: dict[str, Any] | None = None,
        collect_options: dict[int, CollectOptions] | None = None,
        callback_ids: set[int] | None = None,
        filter_ids: set[int] | None = None,
        raw_callback_ids: set[int] | None = None,
        requirements_cache_box: (
            list[dict[int, tuple[bool | CallerInfo, bool | ThreadInfo, bool | ProcessInfo]] | None]
            | None
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
        activation: _ModuleActivation | None = None,
    ) -> None:
        self._inner = inner
        # Per-module enable/disable rules (shared between bound loggers)
        self._activation = activation if activation is not None else _ModuleActivation()
        self._patchers = patchers if patchers is not None else []
        self._context = dict(context or {})
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
        # Box[0] is ``emit_no -> (caller, thread, process)`` or None if invalid
        self._requirements_cache_box: list[
            dict[int, tuple[bool | CallerInfo, bool | ThreadInfo, bool | ProcessInfo]] | None
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
        # False routes every call through the Python dispatch path (tests only)
        self._fast_path = True
        # Identifies this Logger family's table in Rust (see _refresh_fast_collect)
        self._fast_owner = _next_fast_owner()
        self._refresh_fast_collect()

    parse = staticmethod(_parse_file)
    """Parse a log file into dicts of regex named groups (same as ``logust.parse``)."""

    def _invalidate_requirements_cache(self) -> None:
        """Invalidate all caches (call when handlers change)."""
        self._requirements_cache_box[0] = None
        self._aggregated_options_box[0] = None
        self._refresh_fast_collect()

    def _refresh_fast_collect(self) -> None:
        """Tell Rust what ``log_fast`` must collect at each built-in level.

        The level methods hand a plain ``logger.info("msg")`` to
        ``PyLogger.log_fast``, which collects caller/thread/process info itself.
        It can only do so when the effective requirement is ``True`` or
        ``False``; a fixed ``CallerInfo`` / ``ThreadInfo`` / ``ProcessInfo``
        marks the level unavailable so those calls take the Python path. The
        table lives with the handler state shared by bound loggers, and Rust
        resets it whenever a handler or callback changes.
        """
        # A new generation first: a refresh that started earlier, before this
        # logger's bookkeeping changed, can no longer store its table.
        generation = self._inner.invalidate_fast_collect()
        if not self._fast_path:
            return
        table = 0
        for slot, emit_no in enumerate(_FAST_LEVELS):
            nibble = 0
            needs = self._compute_effective_requirements(emit_no)
            for bit, need in zip((1, 2, 4), needs, strict=True):
                if need is True:
                    nibble |= bit
                elif need is not False:
                    nibble = _FAST_UNAVAILABLE
                    break
            table |= nibble << (4 * slot)
        self._inner.set_fast_collect(table, generation, self._fast_owner)

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

        # A copy: another thread may add or remove handlers meanwhile
        for handler_id, opts in self._collect_options.copy().items():
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
        emit_no: int | None = None,
    ) -> tuple[bool | CallerInfo, bool | ThreadInfo, bool | ProcessInfo]:
        """Compute effective requirements considering CollectOptions.

        ``emit_no`` is numeric severity (built-in ``LogLevel`` value or custom ``no``).
        When omitted, uses a conservative merge (``u32::MAX`` in Rust).

        With ``CollectOptions``, results are cached per ``emit_no`` until invalidated.

        When there are no ``CollectOptions``, Rust requirements are scoped to ``emit_no``
        when provided; otherwise the conservative superset getters are used.

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
        eff_emit = _coerce_emit_no_u32(emit_no) if emit_no is not None else _EMIT_NO_SUPERSET

        # Return cached result if available (O(1) hot path, keyed by emit severity)
        cache = self._requirements_cache_box[0]
        if cache is not None:
            cached = cache.get(eff_emit)
            if cached is not None:
                return cached

        if not self._collect_options:
            if emit_no is None:
                return (
                    self._inner.needs_caller_info,
                    self._inner.needs_thread_info,
                    self._inner.needs_process_info,
                )
            return self._inner.collect_needs_for_emit_no(eff_emit)

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

        # Untracked handlers (e.g. default console): emit-scoped handler formats only.
        h_caller, h_thread, h_process = self._inner.handler_only_needs_for_emit_no(eff_emit)
        has_untracked_caller_need = has_untracked_handlers and h_caller
        has_untracked_thread_need = has_untracked_handlers and h_thread
        has_untracked_process_need = has_untracked_handlers and h_process

        merged_caller, merged_thread, merged_proc = self._inner.collect_needs_for_emit_no(eff_emit)

        # Dynamic collection is needed when:
        # 1. Auto-detect (xxx_none) and Rust merge at this emit severity needs it
        # 2. Raw callbacks/filters need full records
        # 3. Untracked handlers may need it
        needs_dynamic_caller = (
            (merged_caller and caller_none) or needs_full_records or has_untracked_caller_need
        )
        needs_dynamic_thread = (
            (merged_thread and thread_none) or needs_full_records or has_untracked_thread_need
        )
        needs_dynamic_process = (
            (merged_proc and process_none) or needs_full_records or has_untracked_process_need
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
        cache_dict = self._requirements_cache_box[0]
        if cache_dict is None:
            cache_dict = {}
            self._requirements_cache_box[0] = cache_dict
        cache_dict[eff_emit] = result
        return result

    def _apply_patchers(
        self,
        *,
        level_name: str,
        level_no: int,
        message: Any,
        exception: str | None,
        extra: dict[str, Any] | None,
    ) -> tuple[str, str | None, dict[str, Any] | None]:
        """Apply registered patchers before the record reaches handlers."""
        message_str = message if isinstance(message, str) else str(message)
        if not self._patchers:
            return message_str, exception, extra

        # ``contextualize()`` values go under the bound ones, as in loguru
        context = _CONTEXT.get(None)
        base_extra = {**context, **self._context} if context else dict(self._context)
        if extra:
            base_extra.update(extra)
        original_extra_keys = {str(key) for key in base_extra}

        level = _PATCH_LEVELS.get(level_name)
        if level is None or level.no != level_no:
            level = self._patch_level_value(level_name, level_no)
        record = _PatchRecord(
            {
                "level": level,
                "level_no": level_no,
                "message": message_str,
                "exception": exception,
                "extra": base_extra,
            }
        )

        for patcher in self._patchers:
            patcher(record)

        # dict.get: these keys are never lazy, so skip the subclass overrides
        patched_exception = dict.get(record, "exception", exception)
        patched_extra = dict.get(record, "extra", extra or {})

        extra_out: dict[str, Any] | None
        if patched_extra is None:
            extra_out = None
        elif type(patched_extra) is dict or isinstance(patched_extra, Mapping):
            extra_out = {str(key): value for key, value in patched_extra.items()}
            # Rust context is additive; blank removed keys so patchers can hide bound values.
            if original_extra_keys:
                for key in original_extra_keys - extra_out.keys():
                    extra_out[key] = ""
            if not extra_out:
                extra_out = None
        else:
            extra_out = extra

        if patched_exception is not None and not isinstance(patched_exception, str):
            patched_exception = str(patched_exception)
        return (
            str(dict.get(record, "message", message_str)),
            # An untouched ``ExceptionText`` keeps its per-handler variants
            patched_exception,
            extra_out,
        )

    def _patch_level_value(self, level_name: str, no: int) -> RecordLevelStr:
        """Build and cache ``record["level"]`` for patchers (cache miss path)."""
        name = level_name.upper()
        info = self._inner.level_info(name)
        icon = (info[3] or "") if info is not None else ""
        value = RecordLevelStr(name, no, icon)
        if len(_PATCH_LEVELS) > 256:
            _PATCH_LEVELS.clear()
        _PATCH_LEVELS[level_name] = value
        return value

    def _inner_for_call(self, extra: dict[str, Any] | None) -> PyLogger:
        """The Rust logger one message logs through, given its extra kwargs.

        Applies loguru's ``extra`` precedence: ``contextualize()`` values of the
        current thread or task, then this logger's bound values (``bind()``,
        ``configure(extra=...)``), then the message's own keyword arguments.
        ``self._inner`` already carries the bound values, so outside any
        ``contextualize()`` block this is a plain ``bind()`` of the kwargs.
        """
        context = _CONTEXT.get(None)
        if not context:
            return self._inner if extra is None else self._inner.bind(extra)
        return self._inner.contextualized(context, extra)

    def _log_with_level(
        self,
        level_value: int,
        level_name: str,
        message: str,
        exception: str | None,
        depth: int,
        kwargs: dict[str, Any] | None = None,
        args: tuple[Any, ...] = (),
    ) -> None:
        # Callers must check ``level_value < self._inner.min_level`` first so a
        # filtered-out call returns before this frame and any arg handling.
        if self._activation.rules and self._activation.caller_disabled(depth + 1):
            return
        extra_kwargs: dict[str, Any] | None = None
        if args or kwargs:
            message, extra_kwargs = _split_kwargs_for_format(message, kwargs or {}, args)
            if not extra_kwargs:
                extra_kwargs = None

        # ``message`` is a plain ``str`` from here on (patchers return one too)
        if self._patchers:
            message, exception, extra_kwargs = self._apply_patchers(
                level_name=level_name,
                level_no=level_value,
                message=message,
                exception=exception,
                extra=extra_kwargs,
            )
        else:
            message = str(message)

        inner = self._inner_for_call(extra_kwargs)

        # Effective requirements considering CollectOptions: the per-emit cache
        # hit is the common case, a miss computes (and caches) them.
        cache = self._requirements_cache_box[0]
        needs = cache.get(level_value) if cache is not None else None
        if needs is None:
            needs = self._compute_effective_requirements(level_value)
        needs_caller, needs_thread, needs_process = needs

        if needs_caller is False and needs_thread is False and needs_process is False:
            if exception is None:
                getattr(inner, level_name)(message)
            else:
                getattr(inner, level_name)(message, exception=exception)
            return

        if needs_thread is False and needs_process is False:
            if needs_caller is True:
                name, function, line, file = _get_caller_info(depth + 1)
            else:
                # needs_caller is CallerInfo (False case already returned above)
                assert isinstance(needs_caller, CallerInfo)
                name, function, line, file = (
                    needs_caller.name,
                    needs_caller.function,
                    needs_caller.line,
                    needs_caller.file,
                )
            if exception is None:
                getattr(inner, level_name)(
                    message, name=name, function=function, line=line, file=file
                )
            else:
                getattr(inner, level_name)(
                    message,
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
            getattr(inner, level_name)(
                message,
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
            getattr(inner, level_name)(
                message,
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
        self,
        message: str,
        *args: Any,
        exception: str | None = None,
        _depth: int = 0,
        **kwargs: Any,
    ) -> None:
        """Output TRACE level log message."""
        if 5 < self._inner.min_level:
            return
        if (
            args
            or kwargs
            or exception is not None
            or self._patchers
            or self._activation.rules
            or not self._inner.log_fast(5, message, _depth + 1, self._fast_owner)
        ):
            self._log_with_level(5, "trace", message, exception, _depth + 1, kwargs, args)

    def debug(
        self,
        message: str,
        *args: Any,
        exception: str | None = None,
        _depth: int = 0,
        **kwargs: Any,
    ) -> None:
        """Output DEBUG level log message."""
        if 10 < self._inner.min_level:
            return
        if (
            args
            or kwargs
            or exception is not None
            or self._patchers
            or self._activation.rules
            or not self._inner.log_fast(10, message, _depth + 1, self._fast_owner)
        ):
            self._log_with_level(10, "debug", message, exception, _depth + 1, kwargs, args)

    def info(
        self,
        message: str,
        *args: Any,
        exception: str | None = None,
        _depth: int = 0,
        **kwargs: Any,
    ) -> None:
        """Output INFO level log message.

        ``message`` is formatted with ``str.format(*args, **kwargs)`` only when
        positional or keyword arguments are given (loguru-compatible); kwargs
        not consumed by placeholders are added to ``extra``.
        """
        if 20 < self._inner.min_level:
            return
        if (
            args
            or kwargs
            or exception is not None
            or self._patchers
            or self._activation.rules
            or not self._inner.log_fast(20, message, _depth + 1, self._fast_owner)
        ):
            self._log_with_level(20, "info", message, exception, _depth + 1, kwargs, args)

    def success(
        self,
        message: str,
        *args: Any,
        exception: str | None = None,
        _depth: int = 0,
        **kwargs: Any,
    ) -> None:
        """Output SUCCESS level log message."""
        if 25 < self._inner.min_level:
            return
        if (
            args
            or kwargs
            or exception is not None
            or self._patchers
            or self._activation.rules
            or not self._inner.log_fast(25, message, _depth + 1, self._fast_owner)
        ):
            self._log_with_level(25, "success", message, exception, _depth + 1, kwargs, args)

    def warning(
        self,
        message: str,
        *args: Any,
        exception: str | None = None,
        _depth: int = 0,
        **kwargs: Any,
    ) -> None:
        """Output WARNING level log message."""
        if 30 < self._inner.min_level:
            return
        if (
            args
            or kwargs
            or exception is not None
            or self._patchers
            or self._activation.rules
            or not self._inner.log_fast(30, message, _depth + 1, self._fast_owner)
        ):
            self._log_with_level(30, "warning", message, exception, _depth + 1, kwargs, args)

    def error(
        self,
        message: str,
        *args: Any,
        exception: str | None = None,
        _depth: int = 0,
        **kwargs: Any,
    ) -> None:
        """Output ERROR level log message."""
        if 40 < self._inner.min_level:
            return
        if (
            args
            or kwargs
            or exception is not None
            or self._patchers
            or self._activation.rules
            or not self._inner.log_fast(40, message, _depth + 1, self._fast_owner)
        ):
            self._log_with_level(40, "error", message, exception, _depth + 1, kwargs, args)

    def fail(
        self,
        message: str,
        *args: Any,
        exception: str | None = None,
        _depth: int = 0,
        **kwargs: Any,
    ) -> None:
        """Output FAIL level log message."""
        if 45 < self._inner.min_level:
            return
        if (
            args
            or kwargs
            or exception is not None
            or self._patchers
            or self._activation.rules
            or not self._inner.log_fast(45, message, _depth + 1, self._fast_owner)
        ):
            self._log_with_level(45, "fail", message, exception, _depth + 1, kwargs, args)

    def critical(
        self,
        message: str,
        *args: Any,
        exception: str | None = None,
        _depth: int = 0,
        **kwargs: Any,
    ) -> None:
        """Output CRITICAL level log message."""
        if 50 < self._inner.min_level:
            return
        if (
            args
            or kwargs
            or exception is not None
            or self._patchers
            or self._activation.rules
            or not self._inner.log_fast(50, message, _depth + 1, self._fast_owner)
        ):
            self._log_with_level(50, "critical", message, exception, _depth + 1, kwargs, args)

    def exception(self, message: str, *args: Any, _depth: int = 0, **kwargs: Any) -> None:
        """Log ERROR with current exception traceback.

        Must be called from within an except block to capture the exception.
        If called outside an except block, logs a plain ERROR message.

        Args:
            message: The error message.
            *args: Positional ``str.format`` arguments for ``message``.
            _depth: Internal depth adjustment for wrapper methods.
            **kwargs: Additional arguments passed to error().

        Examples:
            >>> try:
            ...     risky_operation()
            ... except:
            ...     logger.exception("Operation failed")
            # Output: ERROR with full traceback
        """
        exc_info = current_exc_info()
        if exc_info is not None:
            tb = capture_exception(self._inner, exc_info)
            self.error(message, *args, exception=tb, _depth=_depth + 1, **kwargs)
        else:
            self.error(message, *args, _depth=_depth + 1, **kwargs)

    def level(
        self,
        name: str,
        no: int | None = None,
        color: str | None = None,
        icon: str | None = None,
    ) -> Level:
        """Register, update, or look up a log level.

        - ``level(name, no=..., ...)`` registers a level (or re-registers it).
        - ``level(name)`` returns the level's information.
        - ``level(name, color=..., icon=...)`` without ``no`` updates an existing
          level, including built-in ones.

        Args:
            name: Level name (e.g., "NOTICE"). Case-insensitive.
            no: Numeric severity (higher = more severe).
                Built-in levels: TRACE=5, DEBUG=10, INFO=20, SUCCESS=25,
                WARNING=30, ERROR=40, FAIL=45, CRITICAL=50
            color: Color name (e.g., "cyan", "bright_blue", "red").
            icon: Optional icon symbol for display.

        Returns:
            A ``Level(name, no, color, icon)`` named tuple.

        Raises:
            ValueError: If ``no`` is omitted and the level does not exist.

        Examples:
            >>> logger.level("NOTICE", no=25, color="cyan", icon="...")
            >>> logger.log("NOTICE", "Custom level message")
            >>> logger.level("NOTICE").no
            25
            >>> logger.level("INFO", color="blue")  # Update a built-in level
        """
        existing = self._inner.level_info(name)
        if no is None:
            if existing is None:
                raise ValueError(f"Level '{name}' does not exist")
            if color is None and icon is None:
                return _level_from_info(existing)
            no = existing[1]
        if existing is not None:
            if no != existing[1] and name.lower() in _LEVEL_VALUES:
                raise TypeError(
                    f"Level '{existing[0]}' already exists, you can't update its severity no"
                )
            if color is None and existing[2]:
                color = existing[2]
            if icon is None:
                icon = existing[3]
        self._inner.level(name, no, color, icon)
        _PATCH_LEVELS.clear()
        info = self._inner.level_info(name)
        assert info is not None
        return _level_from_info(info)

    def log(
        self,
        level: str | int,
        message: str,
        *args: Any,
        exception: str | None = None,
        _depth: int = 0,
        **kwargs: Any,
    ) -> None:
        """Log at any level (built-in or custom).

        Args:
            level: Level name (str) or numeric value (int).
            message: Log message. Formatted with ``str.format(*args, **kwargs)``
                only when positional or keyword arguments are given.
            *args: Positional format arguments.
            exception: Optional exception traceback.
            _depth: Internal depth adjustment for wrapper methods.

        Examples:
            >>> logger.log("INFO", "Using built-in level by name")
            >>> logger.log(20, "Using built-in level by number")
            >>> logger.log("INFO", "Processed {} items", 3)
        """
        if isinstance(level, str):
            level_lower = level.lower()
            if level_lower in _LEVEL_VALUES:
                level_value = _LEVEL_VALUES[level_lower]
                if level_value < self._inner.min_level:
                    return
                if (
                    args
                    or kwargs
                    or exception is not None
                    or self._patchers
                    or self._activation.rules
                    or not self._inner.log_fast(level_value, message, _depth + 1, self._fast_owner)
                ):
                    self._log_with_level(
                        level_value,
                        level_lower,
                        message,
                        exception,
                        _depth + 1,
                        kwargs,
                        args,
                    )
                return
        elif isinstance(level, int) and level in _LEVEL_VALUE_MAP:
            if level < self._inner.min_level:
                return
            if (
                args
                or kwargs
                or exception is not None
                or self._patchers
                or self._activation.rules
                or not self._inner.log_fast(level, message, _depth + 1, self._fast_owner)
            ):
                self._log_with_level(
                    level, _LEVEL_VALUE_MAP[level], message, exception, _depth + 1, kwargs, args
                )
            return

        resolved_emit = self._inner.try_resolve_emit_level_no(level)
        if resolved_emit is None:
            extra_kw: dict[str, Any] | None = None
            if self._patchers:
                message, exception, extra_kw = self._apply_patchers(
                    level_name=str(level),
                    level_no=0,
                    message=message,
                    exception=exception,
                    extra=extra_kw,
                )
            else:
                message = str(message)
            inner = self._inner_for_call(extra_kw)
            if exception is None:
                inner.log(level, message)
            else:
                inner.log(level, message, exception=exception)
            return
        if resolved_emit < self._inner.min_level:
            return
        if self._activation.rules and self._activation.caller_disabled(_depth + 1):
            return

        extra_kw = None
        if args or kwargs:
            message, extra_kw = _split_kwargs_for_format(message, kwargs, args)
            if not extra_kw:
                extra_kw = None

        # ``message`` is a plain ``str`` from here on (patchers return one too)
        if self._patchers:
            message, exception, extra_kw = self._apply_patchers(
                level_name=str(level),
                level_no=resolved_emit,
                message=message,
                exception=exception,
                extra=extra_kw,
            )
        else:
            message = str(message)

        cache = self._requirements_cache_box[0]
        needs = cache.get(resolved_emit) if cache is not None else None
        if needs is None:
            needs = self._compute_effective_requirements(resolved_emit)
        needs_caller, needs_thread, needs_process = needs
        inner = self._inner_for_call(extra_kw)

        if needs_caller is False and needs_thread is False and needs_process is False:
            if exception is None:
                inner.log(level, message)
            else:
                inner.log(level, message, exception=exception)
            return

        if needs_thread is False and needs_process is False:
            if needs_caller is True:
                # Custom ``log()`` has no ``info()`` → ``_log_with_level`` wrapper frame.
                name, function, line, file = _get_caller_info(_depth + 1)
            else:
                # needs_caller is CallerInfo (False case already returned above)
                assert isinstance(needs_caller, CallerInfo)
                name, function, line, file = (
                    needs_caller.name,
                    needs_caller.function,
                    needs_caller.line,
                    needs_caller.file,
                )
            if exception is None:
                inner.log(level, message, name=name, function=function, line=line, file=file)
            else:
                inner.log(
                    level,
                    message,
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
            inner.log(
                level,
                message,
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
            inner.log(
                level,
                message,
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
        self._invalidate_requirements_cache()

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

    def enable(
        self,
        name: str | LogLevel | None = None,
        *,
        level: LogLevel | str | None = None,
    ) -> None:
        """Enable messages from a module, or re-enable console logging.

        - ``enable("mylib")`` re-enables messages logged from ``mylib`` and its
          submodules (``mylib.*``) after ``disable("mylib")``, as in loguru.
          ``enable("")`` removes every module rule.
        - ``enable()``, ``enable(LogLevel.Info)``, ``enable("INFO")`` or
          ``enable(level="INFO")`` re-enables console output (logust behavior).
          A built-in level name that ``disable(name)`` made a module rule for
          (a module called ``info``, say) re-enables that module instead.

        A string that is a built-in level name (case-insensitive: ``"trace"``,
        ``"debug"``, ``"info"``, ``"success"``, ``"warning"``, ``"error"``,
        ``"fail"``, ``"critical"``) is treated as a level; any other string is
        a module name.

        Args:
            name: Module name, built-in level, or None.
            level: Minimum console level when re-enabling console output.
        """
        if isinstance(name, str) and (
            name.lower() not in _LEVEL_VALUES or self._activation.has_rule(name)
        ):
            if level is not None:
                raise TypeError("enable() got both a module name and a level")
            self._activation.change(name, True)
            return
        if name is not None:
            if level is not None:
                raise TypeError("enable() got multiple values for the level")
            level = name
        self._inner.enable(_to_log_level(level) if level is not None else None)
        self._invalidate_requirements_cache()

    def disable(self, name: str | None = None) -> None:
        """Disable messages from a module, or disable console logging.

        - ``disable("mylib")`` drops messages logged from ``mylib`` and its
          submodules (``mylib.*``), as in loguru. A more specific
          ``enable("mylib.sub")`` takes precedence. ``disable("")`` disables
          every module.
        - ``disable()`` removes the console handler (logust behavior).

        Args:
            name: Module name, or None to disable console output.
        """
        if name is None:
            self._inner.disable()
            self._invalidate_requirements_cache()
            return
        if not isinstance(name, str):
            raise TypeError(f"Invalid name, it should be a string, not: {type(name).__name__!r}")
        self._activation.change(name, False)

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
        rotation: str | datetime.timedelta | datetime.time | None = None,
        retention: str | int | None = None,
        compression: bool | str = False,
        serialize: bool = False,
        filter: Callable[[dict[str, Any]], bool] | None = None,
        enqueue: bool = False,
        colorize: bool | None = None,
        collect: CollectOptions | None = None,
        mode: str | None = None,
        encoding: str | None = None,
        delay: bool | None = None,
        catch: bool | None = None,
        backtrace: bool = False,
        diagnose: bool = False,
        buffering: int | None = None,
    ) -> int:
        """Add a handler (file, console, or callable sink).

        Args:
            sink: Path to the log file (str or Path object), a stream (any object
                  with a write() method, e.g. sys.stdout or io.StringIO), or a
                  callable that receives formatted log messages. A stream is
                  bound when add() is called; a later swap of sys.stdout is not
                  observed.
            level: Minimum log level for this handler.
            format: Custom format string (e.g., "{time} | {level} | {message}").
            rotation: Rotation strategy ("daily", "hourly", "500 MB", etc.)
                      Also accepts ``timedelta(days=1)`` / ``timedelta(hours=1)``
                      and ``time(0, 0)``; other values raise ValueError.
                      Only valid for file sinks.
            retention: Retention policy ("10 days" or count as int)
                       Only valid for file sinks.
            compression: Compress rotated files. ``True`` means gzip; a string
                         selects the format: "gz", "bz2", "zip", "tar",
                         "tar.gz" or "tar.bz2" ("xz", "lzma" and "tar.xz"
                         raise ValueError). Only valid for file sinks.
            serialize: Output as JSON instead of text format.
            filter: Optional callable that receives a record dict and returns
                    True if the record should be logged, False to skip.
            enqueue: If True, writes are queued and processed asynchronously
                     in a background thread (thread-safe).
                     If False (default), writes are synchronous (reliable).
                     Only valid for file sinks.
            colorize: Enable ANSI color codes and render message color markup.
                      If None, auto-detect for streams (TTY, NO_COLOR,
                      FORCE_COLOR, CI, PyCharm, Jupyter); False for serialize,
                      files, and callables.
            collect: Options for controlling information collection.
                     Can override auto-detection from format string.
            mode: "a" (default) appends, "w" truncates the file when it is
                  first opened. File sinks only.
            encoding: Accepted for loguru compatibility. Files are always
                      written as UTF-8, so only UTF-8 aliases are accepted;
                      anything else raises ValueError. File sinks only.
            delay: If True, the file is not created until the first message
                   is written. File sinks only.
            catch: What to do when the sink fails to write a message.
                   None (default) drops the error silently, True prints a
                   report to stderr (loguru's default), False raises the
                   error from the logging call.
            backtrace: Tracebacks logged by ``exception()``, ``catch()`` and
                       ``opt(exception=True)`` also show the frames above the
                       point where the exception was caught. loguru's default
                       is True.
            diagnose: Those tracebacks also show the values of the variables
                      used on each line. They can contain secrets, so this
                      is off by default (loguru's default is True).
            buffering: As in ``open()``. ``1`` (default) writes each line to
                       the file before the logging call returns, so it
                       survives a crash or a kill. ``N > 1`` keeps up to
                       ``N`` bytes in memory and writes them when the buffer
                       is full, on ``complete()``, ``remove()`` and at normal
                       exit (faster, but a killed process loses them). A
                       negative value means 8192 bytes; ``0`` raises
                       ValueError. Ignored with ``enqueue=True``, which
                       batches writes on its own. File sinks only.

        Returns:
            Handler ID for later removal.

        Raises:
            TypeError: If ``mode``, ``encoding``, ``delay`` or ``buffering``
                is given for a non-file sink.
            ValueError: If ``compression``, ``mode``, ``encoding`` or
                ``buffering`` is not supported.

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
        handler_id = self._add_handler(
            sink,
            level=level,
            format=format,
            rotation=rotation,
            retention=retention,
            compression=compression,
            serialize=serialize,
            filter=filter,
            enqueue=enqueue,
            colorize=colorize,
            collect=collect,
            mode=mode,
            encoding=encoding,
            delay=delay,
            catch=catch,
            buffering=buffering,
        )
        if backtrace or diagnose:
            # Read only when an exception is logged (see _traceback.capture_exception)
            self._inner.set_exception_variant(handler_id, int(backtrace) | (int(diagnose) << 1))
        return handler_id

    def _add_handler(
        self,
        sink: str | os.PathLike[str] | TextIO | Callable[[str], Any],
        *,
        level: LogLevel | str | None,
        format: str | None,
        rotation: str | datetime.timedelta | datetime.time | None,
        retention: str | int | None,
        compression: bool | str,
        serialize: bool,
        filter: Callable[[dict[str, Any]], bool] | None,
        enqueue: bool,
        colorize: bool | None,
        collect: CollectOptions | None,
        mode: str | None,
        encoding: str | None,
        delay: bool | None,
        catch: bool | None,
        buffering: int | None = None,
    ) -> int:
        """Create the handler for ``add()`` and return its ID."""
        if rotation is not None:
            rotation = _rotation_to_str(rotation)

        # A replaced sys.stdout (rich, Jupyter, redirect_stdout) must get output via its write().
        is_console = sink is sys.__stdout__ or sink is sys.__stderr__
        is_stream = callable(getattr(sink, "write", None))
        if colorize is None:
            colorize = not serialize and is_stream and self._should_colorize(cast("TextIO", sink))

        if not is_stream and callable(sink) and _is_coroutine_callable(sink):
            raise TypeError(
                "Coroutine function sinks (async def) are not supported yet: "
                "logust calls sinks synchronously and would never await them. "
                "Use a regular function sink instead."
            )

        is_file = not is_stream and not callable(sink)
        if not is_file:
            file_only = {"mode": mode, "encoding": encoding, "delay": delay, "buffering": buffering}
            for option, value in file_only.items():
                if value is not None:
                    raise TypeError(f"add() got an unexpected keyword argument '{option}'")

        if is_stream and not is_console:
            sink = self._stream_writer(cast("TextIO", sink))

        if callable(sink) and not is_console:
            handler_id = self._add_callable_sink(
                sink,
                level=level,
                format=format,
                serialize=serialize,
                filter=filter,
                colorize=colorize,
                catch=catch,
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

        if is_console:
            stream_name = "stdout" if sink is sys.__stdout__ else "stderr"
            resolved_level = _to_log_level(level) if level is not None else None
            handler_id = self._inner.add_console(
                stream=stream_name,
                level=resolved_level,
                format=format,
                serialize=serialize,
                filter=filter,
                colorize=colorize,
                catch=catch,
            )
            # Always track handler with CollectOptions (default to auto-detect if not specified)
            self._collect_options[handler_id] = collect if collect is not None else CollectOptions()
            if filter is not None:
                self._filter_ids.add(handler_id)
            self._invalidate_requirements_cache()
            return handler_id

        # At this point sink must be a path (str or PathLike), not TextIO
        sink_str = os.fspath(cast("str | os.PathLike[str]", sink))

        if encoding is not None:
            _check_utf8_encoding(encoding)
        if buffering is not None and (
            isinstance(buffering, bool) or not isinstance(buffering, int)
        ):
            raise TypeError(f"buffering must be an int, not {type(buffering).__name__}")
        if callable(compression):
            raise TypeError(
                "callable compression is not supported; pass True or a format string "
                '("gz", "bz2", "zip", "tar", "tar.gz", "tar.bz2")'
            )

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
            colorize=colorize,
            mode=mode,
            delay=delay,
            catch=catch,
            buffering=buffering,
        )
        # Always track handler with CollectOptions (default to auto-detect if not specified)
        self._collect_options[handler_id] = collect if collect is not None else CollectOptions()
        if filter is not None:
            self._filter_ids.add(handler_id)
        self._invalidate_requirements_cache()
        return handler_id

    @staticmethod
    def _should_colorize(stream: TextIO) -> bool:
        """Port of loguru's ``_colorama.should_colorize``."""
        is_standard_stream = stream is sys.stdout or stream is sys.stderr
        is_original_standard_stream = stream is sys.__stdout__ or stream is sys.__stderr__

        if is_standard_stream or is_original_standard_stream:
            if os.getenv("NO_COLOR"):
                return False
            if os.getenv("FORCE_COLOR"):
                return True

        if getattr(builtins, "__IPYTHON__", False) and is_standard_stream:
            iostream = sys.modules.get("ipykernel.iostream")
            if iostream is not None and isinstance(stream, iostream.OutStream):
                return True

        if is_original_standard_stream:
            if "CI" in os.environ and any(
                ci in os.environ
                for ci in ("TRAVIS", "CIRCLECI", "APPVEYOR", "GITLAB_CI", "GITHUB_ACTIONS")
            ):
                return True
            if "PYCHARM_HOSTED" in os.environ:
                return True
            if os.environ.get("TERM", "") == "dumb":
                return False
            if os.name == "nt" and "TERM" in os.environ:
                return True

        try:
            return stream.isatty()
        except Exception:
            return False

    @staticmethod
    def _stream_writer(stream: TextIO) -> Callable[[str], None]:
        flush = getattr(stream, "flush", None)
        if not callable(flush):
            flush = None

        def write(message: str) -> None:
            stream.write(message + "\n")
            if flush is not None:
                flush()

        return write

    def _add_callable_sink(
        self,
        sink: Callable[[str], Any],
        *,
        level: LogLevel | str | None = None,
        format: str | None = None,
        serialize: bool = False,
        filter: Callable[[dict[str, Any]], bool] | None = None,
        colorize: bool = False,
        catch: bool | None = None,
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
            colorize: Style tokens and render message markup as ANSI codes.
            catch: None silently drops sink errors, True reports them to
                   stderr, False propagates them to the logging call.

        Returns:
            Handler ID for later removal.
        """
        import json

        resolved_level = _to_log_level(level) if level is not None else None
        default_format = "{time} | {level:<8} | {name}:{function}:{line} - {message}"
        template_str = format or default_format

        # Pre-parse template for efficient single-pass formatting
        parsed_template = ParsedCallableTemplate(template_str, colorize)
        render = parsed_template.render

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
                    # Format using the pre-parsed template (compiled renderer)
                    formatted = render(record)

                sink(formatted)
            except Exception:
                # catch=None (default): silently ignore sink errors
                pass

        wrapper: Callable[[dict[str, Any]], None] = callback_wrapper
        handler_id_box: list[int | None] = [None]
        if catch is not None:
            # catch=True/False wrappers are chosen once here, so the default
            # wrapper above stays untouched (no extra per-message call).
            def emit(record: dict[str, Any]) -> None:
                if filter is not None and not filter(record):
                    return
                if serialize:
                    json_record: dict[str, Any] = {
                        "time": record.get("timestamp", ""),
                        "level": record.get("level", ""),
                        "message": record.get("message", ""),
                    }
                    for key in ("name", "function", "line", "extra", "exception"):
                        if record.get(key):
                            json_record[key] = record[key]
                    sink(json.dumps(json_record))
                else:
                    sink(render(record))

            if catch:

                def reporting_wrapper(record: dict[str, Any]) -> None:
                    try:
                        emit(record)
                    except Exception:
                        _report_sink_error(handler_id_box[0], record)

                wrapper = reporting_wrapper
            else:
                # catch=False: exceptions propagate through Rust to the caller.
                wrapper = emit

        raise_errors = catch is False
        # Lightweight path: Rust builds a minimal dict; filter/JSON need full dict.
        if filter is None and not serialize:
            flags = parsed_template.lightweight_requirements_for_rust()
            extra_keys = parsed_template.lightweight_extra_keys_for_rust()
            handler_id = self._inner.add_formatted_sink_callback(
                wrapper, flags, extra_keys, resolved_level, raise_errors=raise_errors
            )
        # Filter callbacks always observe the loguru-compatible text view of
        # extras; only filterless serialized sinks get the typed JSON dict.
        elif serialize and filter is None:
            handler_id = self._inner.add_serialized_callback(
                wrapper, resolved_level, raise_errors=raise_errors
            )
        else:
            handler_id = self._inner.add_callback(
                wrapper,
                resolved_level,
                file_path=not serialize and parsed_template.needs_file_path,
                raise_errors=raise_errors,
                extra_repr=not serialize and parsed_template.needs_extra_repr,
            )
        if catch is not None:
            handler_id_box[0] = handler_id
        return handler_id

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

    def _with_inner(
        self,
        inner: PyLogger,
        *,
        context: dict[str, Any] | None = None,
        patchers: list[Callable[[dict[str, Any]], None]] | None = None,
    ) -> Logger:
        """Logger sharing this one's handler state, logging through ``inner``.

        ``context`` defaults to a copy of this logger's and ``patchers`` to the
        same list; the handler bookkeeping is shared like ``bind()`` does.
        Attributes are assigned directly because ``bind()`` runs per message
        and ``__init__``'s keyword plumbing costs more than the copy itself.
        """
        new = Logger.__new__(Logger)
        new._inner = inner
        new._activation = self._activation
        new._patchers = self._patchers if patchers is None else patchers
        new._context = dict(self._context) if context is None else context
        new._collect_options = self._collect_options
        new._callback_ids = self._callback_ids
        new._filter_ids = self._filter_ids
        new._raw_callback_ids = self._raw_callback_ids
        new._requirements_cache_box = self._requirements_cache_box
        new._aggregated_options_box = self._aggregated_options_box
        new._fast_path = self._fast_path
        new._fast_owner = self._fast_owner
        return new

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
        return self._with_inner(
            self._inner.bind(kwargs),
            context={**self._context, **kwargs},
            patchers=self._patchers.copy(),
        )

    @contextmanager
    def contextualize(self, **kwargs: Any) -> Generator[Logger, None, None]:
        """Add context values to every message logged inside a ``with`` block.

        The values live in a :mod:`contextvars` variable, as in loguru: they
        are seen only by the current thread or asyncio task (and by tasks it
        starts inside the block), by every logger, bound or not, including the
        module-level ``logust.info(...)``. Nested blocks merge their values,
        and each block restores the previous ones when it exits. ``bind()``
        values and a message's own keyword arguments take precedence over
        contextualized values with the same key.

        Args:
            **kwargs: Key-value pairs to add to ``extra`` inside the block.

        Yields:
            This logger (it reads the context on each call).

        Examples:
            >>> with logger.contextualize(request_id="abc"):
            ...     logger.info("Processing")  # includes request_id
            >>> logger.info("Done")  # no request_id
        """
        previous = _CONTEXT.get(None)
        # A new dict each time: the stored dicts are never mutated, so tasks
        # that copied the context keep seeing the values they started with
        token = _set_context({**previous, **kwargs} if previous else kwargs)
        try:
            yield self
        finally:
            try:
                _CONTEXT.reset(token)
            except ValueError:
                # Exited in another context than it was entered in (e.g. a
                # generator finalized by a different task): restore by value
                _set_context(previous)

    @overload
    def catch(
        self,
        exception: type[BaseException] | tuple[type[BaseException], ...] = Exception,
        *,
        level: str | int = "ERROR",
        reraise: bool = False,
        onerror: Callable[[BaseException], Any] | None = None,
        exclude: type[BaseException] | tuple[type[BaseException], ...] | None = None,
        default: Any = None,
        message: str = "An error occurred",
    ) -> Catcher: ...

    @overload
    def catch(self, exception: _F) -> _F: ...

    def catch(
        self,
        exception: (
            type[BaseException] | tuple[type[BaseException], ...] | Callable[..., Any]
        ) = Exception,
        *,
        level: str | int = "ERROR",
        reraise: bool = False,
        onerror: Callable[[BaseException], Any] | None = None,
        exclude: type[BaseException] | tuple[type[BaseException], ...] | None = None,
        default: Any = None,
        message: str = "An error occurred",
    ) -> Any:
        """Catch and log exceptions, as a decorator or a context manager.

        Args:
            exception: Exception type(s) to catch. If a function is passed
                instead (``@logger.catch`` without parentheses), it is decorated
                with the default options.
            level: Log level (name or number) for the error message.
            reraise: Whether to re-raise the exception after logging.
            onerror: Called with the exception after it is logged.
            exclude: Exception type(s) that propagate without being logged.
            default: Return value of the decorated function when an exception
                was caught and not re-raised.
            message: Custom message prefix.

        Returns:
            A ``Catcher`` usable as a decorator or a context manager.

        Examples:
            >>> @logger.catch
            ... def risky_function():
            ...     raise ValueError("Something went wrong")
            >>> risky_function()  # Logs the exception, returns None

            >>> @logger.catch(ValueError, level="WARNING", default=-1)
            ... def parse(text):
            ...     return int(text)

            >>> with logger.catch(reraise=True):
            ...     raise RuntimeError("Critical error")  # Logs and re-raises
        """
        if callable(exception) and not (
            isinstance(exception, type) and issubclass(exception, BaseException)
        ):
            catcher = Catcher(self, Exception, exclude, level, reraise, onerror, message, default)
            return catcher(exception)

        return Catcher(
            self,
            exception,
            exclude,
            level,
            reraise,
            onerror,
            message,
            default,
        )

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
        return self._with_inner(self._inner, patchers=[*self._patchers, patcher])

    def configure(
        self,
        *,
        handlers: list[dict[str, Any]] | None = None,
        levels: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
        patcher: Callable[[dict[str, Any]], None] | None = None,
        activation: list[tuple[str, bool]] | None = None,
    ) -> list[int]:
        """Configure the logger from dictionaries.

        Args:
            handlers: List of handler configurations. Each dict can have:
                - sink (required): File path or sys.stdout/sys.stderr
                - level: Minimum log level
                - format: Format string
                - rotation: Rotation strategy (file sinks only; str,
                  timedelta, or time)
                - retention: Retention policy (file sinks only)
                - compression: True (gzip) or a format such as "zip" or
                  "tar.gz" (file sinks only)
                - serialize: Output as JSON
                - filter: Filter function
                - enqueue: Async writes (file sinks only, default False)
                - colorize: Enable ANSI colors (auto-detected for streams)
                - mode: "a" (default) or "w" (file sinks only)
                - encoding: UTF-8 aliases only (file sinks only)
                - delay: Create the file on the first message (file sinks only)
                - buffering: 1 (default) writes each line, N > 1 buffers N bytes
                  (file sinks only)
                - catch: None (drop), True (report to stderr) or False (raise)
                  for sink errors
                - backtrace / diagnose: Traceback detail (default False)
            levels: List of level configurations. Each dict can have:
                - name (required): Level name
                - no: Numeric value (required for a new level; omit it to
                  update the color/icon of an existing level)
                - color: Color name
                - icon: Icon symbol
            extra: Default extra fields to bind
            patcher: Default patcher function
            activation: ``(module_name, enabled)`` pairs applied in order
                with ``enable(name)`` / ``disable(name)``

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
                if name:
                    self.level(
                        name,
                        no=level_config.get("no"),
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
                        mode=handler_config.get("mode"),
                        encoding=handler_config.get("encoding"),
                        delay=handler_config.get("delay"),
                        catch=handler_config.get("catch"),
                        buffering=handler_config.get("buffering"),
                        backtrace=handler_config.get("backtrace", False),
                        diagnose=handler_config.get("diagnose", False),
                    )
                    handler_ids.append(handler_id)

        if extra:
            new_inner = self._inner.bind(extra)
            self._inner = new_inner
            self._context.update(extra)

        if patcher:
            self._patchers.append(patcher)

        if activation:
            for module_name, enabled in activation:
                if not isinstance(module_name, str):
                    raise TypeError(
                        "Invalid activation name, it should be a string, "
                        f"not: {type(module_name).__name__!r}"
                    )
                self._activation.change(module_name, bool(enabled))

        return handler_ids

    def opt(
        self,
        *,
        lazy: bool = False,
        exception: bool = False,
        depth: int = 0,
        backtrace: bool = False,
        diagnose: bool = False,
        colors: bool | None = None,
        capture: bool = True,
    ) -> OptLogger:
        """Return a logger with per-message options.

        Args:
            lazy: Defer callable argument evaluation until message is emitted.
                  Useful for expensive computations that should only run if
                  the log level is enabled.
            exception: Auto-capture current exception traceback.
            depth: Stack frame adjustment (reserved for future use).
            backtrace: Extend trace beyond catch point to show full call stack.
                Applies to every handler, on top of ``add(backtrace=...)``.
            diagnose: Show variable values at each stack frame.
                Applies to every handler, on top of ``add(diagnose=...)``.
            colors: ``False`` keeps color markup in the message as plain text
                for this call. ``True`` (or ``None``, the default) renders it:
                logust always parses message markup, while loguru only does
                so with ``colors=True``.
            capture: ``False`` uses keyword arguments only to format the
                message instead of also adding them to ``extra``.

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
            colors=colors,
            capture=capture,
        )
