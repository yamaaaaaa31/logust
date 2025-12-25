"""Enhanced traceback formatting with backtrace and diagnose support."""

from __future__ import annotations

import linecache
import sys
from types import FrameType, TracebackType


def format_enhanced_traceback(
    backtrace: bool = False,
    diagnose: bool = False,
) -> str:
    """Format exception with optional backtrace and diagnose.

    Args:
        backtrace: Include frames beyond the catch point.
        diagnose: Show variable values at each frame.

    Returns:
        Formatted traceback string.
    """
    exc_info = sys.exc_info()
    if exc_info[0] is None:
        return ""

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
            filename = f.f_code.co_filename
            if "logust" not in filename:
                outer_frames.append((f, f.f_lineno))
            f = f.f_back
        outer_frames = outer_frames[::-1]
        frames = outer_frames + frames

    for frame, lineno in frames:
        filename = frame.f_code.co_filename
        funcname = frame.f_code.co_name

        if "logust" in filename:
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
    if exc_type is not None:
        lines.append(f"{exc_type.__name__}: {exc_value}")

    return "\n".join(lines)
