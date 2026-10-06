"""Traceback formatting: plain, backtrace, and diagnose variants."""

from __future__ import annotations

import builtins
import linecache
import os
import re
import sys
import traceback
from types import FrameType, TracebackType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._logust import PyLogger

ExcInfo = tuple[type[BaseException], BaseException, TracebackType | None]

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
# Modules whose frames are logust plumbing (``catch_wrapper``, ``OptLogger._log``, ...).
# ``logust.contrib`` frames are real application frames and stay visible.
_INTERNAL_FILES = frozenset(
    os.path.join(_PACKAGE_DIR, name)
    for name in ("__init__.py", "_logger.py", "_opt.py", "_traceback.py")
)


def _is_internal(filename: str) -> bool:
    return filename in _INTERNAL_FILES


class ExceptionText(str):
    """Traceback text that also carries per-handler variants.

    The string value is the record's traceback (what patchers, filters and
    raw callbacks see). ``variants[v]`` is the text for handlers added with
    traceback variant ``v`` (bit 0: backtrace, bit 1: diagnose), or None when
    they get the record's text. The Rust core reads ``variants``.
    """

    variants: tuple[str | None, str | None, str | None, str | None]


def _strip_internal_frames(te: traceback.TracebackException, seen: set[int]) -> None:
    """Drop logust's own frames from ``te`` and its chained exceptions."""
    while te is not None and id(te) not in seen:
        seen.add(id(te))
        stack = te.stack
        if any(_is_internal(frame.filename) for frame in stack):
            te.stack = traceback.StackSummary.from_list(
                [frame for frame in stack if not _is_internal(frame.filename)]
            )
        for group_member in getattr(te, "exceptions", None) or ():
            _strip_internal_frames(group_member, seen)
        if te.__cause__ is not None:
            _strip_internal_frames(te.__cause__, seen)
        te = te.__context__  # type: ignore[assignment]


def format_plain_traceback(exc_info: ExcInfo) -> str:
    """Standard ``traceback.format_exception`` output without logust's frames."""
    _, exc_value, tb = exc_info
    te = traceback.TracebackException(type(exc_value), exc_value, tb, compact=True)
    _strip_internal_frames(te, set())
    return "".join(te.format())


# Identical consecutive frames shown before collapsing, as ``traceback`` does
_RECURSIVE_CUTOFF = 3
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MAX_REPR = 50


def _exception_only(exc: BaseException) -> str:
    """``Type: message`` like the plain traceback (module-qualified, notes,
    ``<exception str() failed>`` when ``__str__`` raises)."""
    return "".join(traceback.format_exception_only(type(exc), exc)).rstrip("\n")


def _frame_lines(frame: FrameType, lineno: int, diagnose: bool) -> list[str]:
    code = frame.f_code
    lines = [f'  File "{code.co_filename}", line {lineno}, in {code.co_name}']
    source = linecache.getline(code.co_filename, lineno).strip()
    if not source:
        return lines
    lines.append(f"    {source}")
    if not diagnose:
        return lines
    names = set(_IDENTIFIER.findall(source))
    try:
        local_vars = dict(frame.f_locals)
    except Exception:
        return lines
    for var_name, var_value in local_vars.items():
        if var_name not in names or var_name.startswith("_"):
            continue
        try:
            value_repr = repr(var_value)
        except Exception:
            value_repr = "<repr failed>"
        if len(value_repr) > _MAX_REPR:
            value_repr = value_repr[: _MAX_REPR - 3] + "..."
        lines.append(f"    | {var_name} = {value_repr}")
    return lines


def _format_one(
    exc: BaseException, tb: TracebackType | None, backtrace: bool, diagnose: bool
) -> list[str]:
    """Frames and the exception line of one exception (no chain)."""
    frames: list[tuple[FrameType, int]] = []
    while tb is not None:
        frames.append((tb.tb_frame, tb.tb_lineno))
        tb = tb.tb_next

    if backtrace and frames:
        outer_frames: list[tuple[FrameType, int]] = []
        f: FrameType | None = frames[0][0].f_back
        while f is not None:
            outer_frames.append((f, f.f_lineno))
            f = f.f_back
        frames = outer_frames[::-1] + frames

    lines: list[str] = []
    if frames:
        lines.append("Traceback (most recent call last):")
    last: tuple[str, int, str] | None = None
    count = 0

    def flush_repeats() -> None:
        if count > _RECURSIVE_CUTOFF:
            more = count - _RECURSIVE_CUTOFF
            lines.append(f"  [Previous line repeated {more} more time{'s' if more > 1 else ''}]")

    for frame, lineno in frames:
        code = frame.f_code
        if _is_internal(code.co_filename):
            continue
        key = (code.co_filename, lineno, code.co_name)
        if key == last:
            count += 1
            if count > _RECURSIVE_CUTOFF:
                continue
        else:
            flush_repeats()
            last, count = key, 1
        lines.extend(_frame_lines(frame, lineno, diagnose))
    flush_repeats()

    lines.append(_exception_only(exc))
    members = getattr(exc, "exceptions", None) if _is_group(exc) else None
    for index, member in enumerate(members or (), 1):
        lines.append(f"  +---------------- {index} ----------------")
        member_text = _format_chain(member, member.__traceback__, False, diagnose, set())
        lines.extend(f"    | {line}" for line in member_text.splitlines())
    return lines


def _is_group(exc: BaseException) -> bool:
    group_type = getattr(builtins, "BaseExceptionGroup", None)
    return group_type is not None and isinstance(exc, group_type)


def _format_chain(
    exc: BaseException,
    tb: TracebackType | None,
    backtrace: bool,
    diagnose: bool,
    seen: set[int],
) -> str:
    """``exc`` preceded by its cause or context, as the plain traceback orders them."""
    seen.add(id(exc))
    parts: list[str] = []
    cause, context = exc.__cause__, exc.__context__
    if cause is not None and id(cause) not in seen:
        parts.append(_format_chain(cause, cause.__traceback__, False, diagnose, seen))
        parts.append("\nThe above exception was the direct cause of the following exception:\n")
    elif context is not None and not exc.__suppress_context__ and id(context) not in seen:
        parts.append(_format_chain(context, context.__traceback__, False, diagnose, seen))
        parts.append("\nDuring handling of the above exception, another exception occurred:\n")
    parts.append("\n".join(_format_one(exc, tb, backtrace, diagnose)))
    return "\n".join(parts)


def format_enhanced_traceback(
    backtrace: bool = False,
    diagnose: bool = False,
    exc_info: ExcInfo | None = None,
) -> str:
    """Format exception with optional backtrace and diagnose.

    Chained causes/contexts and exception group members are included like the
    plain traceback; repeated recursive frames are collapsed.

    Args:
        backtrace: Include frames beyond the catch point.
        diagnose: Show variable values at each frame.
        exc_info: Exception to format; defaults to ``sys.exc_info()``.

    Returns:
        Formatted traceback string.
    """
    if exc_info is None:
        current = sys.exc_info()
        if current[0] is None or current[1] is None:
            return ""
        exc_info = (current[0], current[1], current[2])
    _, exc_value, tb = exc_info
    return _format_chain(exc_value, tb, backtrace, diagnose, set())


def _render(exc_info: ExcInfo, variant: int) -> str:
    if variant == 0:
        return format_plain_traceback(exc_info)
    return format_enhanced_traceback(
        backtrace=bool(variant & 1), diagnose=bool(variant & 2), exc_info=exc_info
    )


def capture_exception(
    inner: PyLogger,
    exc_info: ExcInfo,
    *,
    backtrace: bool = False,
    diagnose: bool = False,
) -> str:
    """Format the exception once per traceback variant the handlers need.

    ``backtrace`` / ``diagnose`` come from ``opt()`` and apply to every
    handler on top of the handler's own ``add(backtrace=, diagnose=)``.
    Only the exception path calls this.
    """
    call_variant = int(backtrace) | (int(diagnose) << 1)
    base = _render(exc_info, call_variant)
    mask = inner.exception_variant_mask
    if mask <= 1:
        # Every handler uses the plain traceback
        return base

    rendered: dict[int, str] = {call_variant: base}
    variants: list[str | None] = [None, None, None, None]
    for handler_variant in (1, 2, 3):
        if not mask & (1 << handler_variant):
            continue
        effective = handler_variant | call_variant
        if effective == call_variant:
            continue
        text = rendered.get(effective)
        if text is None:
            text = rendered[effective] = _render(exc_info, effective)
        variants[handler_variant] = text

    if all(text is None for text in variants):
        return base
    result = ExceptionText(base)
    result.variants = (variants[0], variants[1], variants[2], variants[3])
    return result


def current_exc_info() -> ExcInfo | None:
    """``sys.exc_info()`` narrowed to an active exception, or None."""
    exc_type, exc_value, tb = sys.exc_info()
    if exc_type is None or exc_value is None:
        return None
    return (exc_type, exc_value, tb)
