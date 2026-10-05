"""Traceback formatting: plain, backtrace, and diagnose variants."""

from __future__ import annotations

import linecache
import os
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


def format_enhanced_traceback(
    backtrace: bool = False,
    diagnose: bool = False,
    exc_info: ExcInfo | None = None,
) -> str:
    """Format exception with optional backtrace and diagnose.

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

    lines: list[str] = ["Traceback (most recent call last):"]

    tb: TracebackType | None = exc_info[2]
    frames: list[tuple[FrameType, int]] = []
    while tb is not None:
        frames.append((tb.tb_frame, tb.tb_lineno))
        tb = tb.tb_next

    if backtrace and frames:
        first_frame = frames[0][0]
        outer_frames: list[tuple[FrameType, int]] = []
        f: FrameType | None = first_frame.f_back
        while f is not None:
            outer_frames.append((f, f.f_lineno))
            f = f.f_back
        outer_frames = outer_frames[::-1]
        frames = outer_frames + frames

    for frame, lineno in frames:
        filename = frame.f_code.co_filename
        funcname = frame.f_code.co_name

        if _is_internal(filename):
            continue

        lines.append(f'  File "{filename}", line {lineno}, in {funcname}')

        try:
            source = linecache.getline(filename, lineno).strip()
            if source:
                lines.append(f"    {source}")

                if diagnose:
                    local_vars = frame.f_locals
                    shown_vars: set[str] = set()
                    for var_name, var_value in local_vars.items():
                        if (
                            var_name in source
                            and not var_name.startswith("_")
                            and var_name not in shown_vars
                        ):
                            shown_vars.add(var_name)
                            value_repr = repr(var_value)
                            if len(value_repr) > 50:
                                value_repr = value_repr[:47] + "..."
                            lines.append(f"    | {var_name} = {value_repr}")
        except Exception:
            pass

    exc_type, exc_value, _ = exc_info
    lines.append(f"{exc_type.__name__}: {exc_value}")

    return "\n".join(lines)


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
