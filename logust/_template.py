"""Pre-parsed template for callable sinks.

Provides efficient single-pass formatting by parsing the template once
at sink creation time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ._logust import (
    TimeFormatter,
    apply_color_markup,
    check_format_template,
    colorize_level,
    level_details,
    level_style,
    split_format_markup,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# Known format tokens (shared with _logger.py for auto-detect)
# Order doesn't matter; used to build regex pattern (it requires the closing brace,
# so "level" and "level.no" don't shadow each other)
KNOWN_TOKENS: tuple[str, ...] = (
    "time",
    "level",
    "level.name",
    "level.no",
    "level.icon",
    "name",
    "module",
    "function",
    "line",
    "file",
    "file.name",
    "file.path",
    "elapsed",
    "thread",
    "thread.name",
    "thread.id",
    "process",
    "process.name",
    "process.id",
    "message",
    "exception",
)

_RESET = "\x1b[0m"

# Must match the console token styles in src/format.rs.
_TOKEN_STYLES: dict[str, str] = {
    "time": "\x1b[2m",
    "time:spec": "\x1b[2m",
    "elapsed": "\x1b[2m",
    "name": "\x1b[36m",
    "module": "\x1b[36m",
    "function": "\x1b[36m",
    "line": "\x1b[36m",
    "file": "\x1b[36m",
    "file.path": "\x1b[36m",
    "thread": "\x1b[36m",
    "thread.name": "\x1b[36m",
    "thread.id": "\x1b[36m",
    "process": "\x1b[36m",
    "process.name": "\x1b[36m",
    "process.id": "\x1b[36m",
}

# Tokens that require caller info collection
CALLER_TOKENS: frozenset[str] = frozenset(
    {"name", "module", "function", "line", "file", "file.name", "file.path"}
)
# Tokens that require thread / process info collection
THREAD_TOKENS: frozenset[str] = frozenset({"thread", "thread.name", "thread.id"})
PROCESS_TOKENS: frozenset[str] = frozenset({"process", "process.name", "process.id"})
# Tokens rendered exactly like another token (segment key is the target)
_TOKEN_ALIASES: dict[str, str] = {"level.name": "level", "file.name": "file"}
# Segment key of `{time:<spec>}` (rendered through a compiled TimeFormatter)
_TIME_SPEC_KEY = "time:spec"
# Segment key of `{extra}` (the whole extra dict)
_EXTRA_ALL_KEY = "extra:all"


def _format_styled(styled: str, plain: str, spec: str) -> str:
    """``format(plain, spec)`` with ``styled`` (``plain`` with ANSI codes) in
    place of ``plain``: escape codes take no width.

    Matches the Rust formatter: if the spec cuts ``plain`` (a precision), the
    plain result is returned (a cut could split an escape code).
    """
    padded = format(plain, spec)
    pad = len(padded) - len(plain)
    if len(spec) > 1 and spec[1] in "<>^":
        align = spec[1]
    elif spec and spec[0] in "<>^":
        align = spec[0]
    else:
        align = "<"
    left = 0 if align == "<" else pad if align == ">" else pad // 2
    if pad < 0 or padded[left : left + len(plain)] != plain:
        return padded
    return padded[:left] + styled + padded[left + len(plain) :]


def _py_repr_extra(extra: Any) -> str:
    """Fallback `{extra}` rendering for records without Rust's ``extra_repr``.

    Matches ``write_extra_repr`` in src/handler.rs: keys sorted, values as in
    ``str(dict)``.
    """
    if not isinstance(extra, dict):
        return "{}"
    return str({key: extra[key] for key in sorted(extra)})


@dataclass(frozen=True, slots=True)
class LiteralSegment:
    """A literal text segment in the template."""

    text: str


@dataclass(frozen=True, slots=True)
class TokenSegment:
    """A token placeholder in the template."""

    key: str
    spec: str | None = None
    is_extra: bool = False
    extra_key: str | None = None
    # Inside template color markup: the markup's color wins over the default token style
    in_markup: bool = False
    # Compiled `{time:<spec>}` (key "time:spec"; the spec is a loguru time format)
    time_formatter: TimeFormatter | None = None


@dataclass(frozen=True, slots=True)
class StyleSegment:
    """An opening color markup tag in the template.

    ``ansi`` is the ANSI prefix, or None for ``<level>`` (the record's level color).
    """

    ansi: str | None


@dataclass(frozen=True, slots=True)
class StyleEndSegment:
    """A closing color markup tag in the template."""


# Type alias for segment types
Segment = LiteralSegment | TokenSegment | StyleSegment | StyleEndSegment


class ParsedCallableTemplate:
    """Pre-parsed format template for callable sinks.

    Parses the template once at creation time and provides efficient
    single-pass formatting. This avoids the overhead of multiple
    .replace() calls and repeated regex matching.

    Performance improvement: ~1-2us/log for callable sinks.
    """

    __slots__ = (
        "_colorize",
        "_has_exception",
        "_needed_tokens",
        "_needs_extra",
        "_needs_process",
        "_needs_thread",
        "_segments",
        "render",
    )

    # Token pattern: {token} or {token:spec} or {extra[key]} or {extra[key]:spec} or {extra}
    # Only matches known tokens to preserve unknown patterns as literals
    # extra[...] allows any characters except ] (supports hyphens, dots, unicode, etc.)
    # Built from KNOWN_TOKENS to ensure consistency with auto-detect
    _TOKEN_PATTERN = re.compile(
        r"\{("
        + "|".join(re.escape(t) for t in KNOWN_TOKENS)
        + r"|extra\[[^\]]+\]|extra)(?::([^}]*))?\}"
    )

    def __init__(self, template: str, colorize: bool = False) -> None:
        """Parse the template into segments.

        Args:
            template: Format template string.
            colorize: Style tokens and render message markup as ANSI codes.
        """
        self._colorize = colorize
        # Raise ValueError for an invalid `{field:spec}` now (like file and
        # console sinks) instead of rendering the value unformatted per record
        check_format_template(template)
        self._segments: tuple[Segment, ...] = self._parse(template)
        # Pre-compute which tokens are needed for lazy evaluation
        self._needed_tokens: frozenset[str] = frozenset(
            seg.key for seg in self._segments if isinstance(seg, TokenSegment)
        )
        # <level> markup needs the level name even without a {level} token
        if any(isinstance(seg, StyleSegment) and seg.ansi is None for seg in self._segments):
            self._needed_tokens |= {"level"}
        self._needs_extra = "extra" in self._needed_tokens
        # `{thread}` / `{process}` render "name:id" (pre-formatted once per record)
        self._needs_thread = "thread" in self._needed_tokens
        self._needs_process = "process" in self._needed_tokens
        # The template places the exception itself: don't append it
        self._has_exception = "exception" in self._needed_tokens
        # Fastest renderer for this template: a compiled f-string when the
        # template has no color markup, otherwise the segment loop
        self.render: Callable[[dict[str, Any]], str] = self._format_segments
        if not colorize:
            compiled = _compile_renderer(self._segments, self._has_exception, self.render)
            if compiled is not None:
                self.render = compiled

    @property
    def needs_extra_repr(self) -> bool:
        """Whether the template uses ``{extra}`` (records must carry ``extra_repr``)."""
        return _EXTRA_ALL_KEY in self._needed_tokens

    @property
    def needs_file_path(self) -> bool:
        """Whether the template uses ``{file.path}`` (records must carry ``file_path``)."""
        return "file.path" in self._needed_tokens

    def _parse(self, template: str) -> tuple[Segment, ...]:
        """Parse template into literal, token, and color markup segments.

        Color markup is resolved in Rust (shared with the console/file formatter).
        Without colorize the markup segments are dropped, so the tags are stripped.

        Args:
            template: Format template string.

        Returns:
            Tuple of segments (immutable for performance).
        """
        segments: list[Segment] = []
        depth = 0

        for kind, value in split_format_markup(template):
            if kind == "text":
                self._parse_tokens(value, depth > 0, segments)
            elif kind == "close":
                depth -= 1
                if self._colorize:
                    segments.append(StyleEndSegment())
            else:
                depth += 1
                if self._colorize:
                    segments.append(StyleSegment(value if kind == "open" else None))

        return tuple(segments)

    def _parse_tokens(self, template: str, in_markup: bool, segments: list[Segment]) -> None:
        """Append literal and token segments for a markup-free piece of the template."""
        last_end = 0

        for match in self._TOKEN_PATTERN.finditer(template):
            # Add literal before this match
            if match.start() > last_end:
                segments.append(LiteralSegment(template[last_end : match.start()]))

            key = match.group(1)
            spec = match.group(2)

            if key == "extra":
                if spec is None:
                    segments.append(TokenSegment(_EXTRA_ALL_KEY, None, False, None, in_markup))
                else:
                    # Like the Rust formatter: `{extra:<spec>}` is not a field
                    segments.append(LiteralSegment(match.group(0)))
            elif key.startswith("extra["):
                extra_key = key[6:-1]  # Extract key from extra[key]
                segments.append(TokenSegment("extra", spec, True, extra_key, in_markup))
            elif key == "time" and spec is not None:
                # Compiled once here; raises ValueError for an invalid spec (like loguru)
                segments.append(
                    TokenSegment(_TIME_SPEC_KEY, None, False, None, in_markup, TimeFormatter(spec))
                )
            else:
                key = _TOKEN_ALIASES.get(key, key)
                segments.append(TokenSegment(key, spec, False, None, in_markup))

            last_end = match.end()

        # Add remaining literal
        if last_end < len(template):
            segments.append(LiteralSegment(template[last_end:]))

    def lightweight_requirements_for_rust(self) -> tuple[bool, ...]:
        """Booleans for Rust `FormattedSinkRequirements` / `build_mini_record_dict`.

        Order: timestamp, level, name, function, line, file, elapsed, thread, process,
        message, nested extra, file path, extra repr. Must match ``src/lib.rs``
        ``FormattedSinkRequirements``.
        """
        nt = self._needed_tokens
        return (
            "time" in nt or _TIME_SPEC_KEY in nt,
            "level" in nt or "level.no" in nt or "level.icon" in nt,
            ("name" in nt) or ("module" in nt),
            "function" in nt,
            "line" in nt,
            "file" in nt,
            "elapsed" in nt,
            bool(nt & THREAD_TOKENS),
            bool(nt & PROCESS_TOKENS),
            "message" in nt,
            self._needs_extra,
            "file.path" in nt,
            _EXTRA_ALL_KEY in nt,
        )

    def lightweight_extra_keys_for_rust(self) -> tuple[str, ...]:
        """``extra[key]`` names for Rust ``FormattedSinkRequirements.extra_keys``.

        Order preserved, unique.
        """
        keys: list[str] = []
        seen: set[str] = set()
        for seg in self._segments:
            if isinstance(seg, TokenSegment) and seg.is_extra and seg.extra_key:
                if seg.extra_key not in seen:
                    seen.add(seg.extra_key)
                    keys.append(seg.extra_key)
        return tuple(keys)

    def format(self, record: dict[str, Any]) -> str:
        """Format the record using the pre-parsed template.

        Args:
            record: Log record dictionary.

        Returns:
            Formatted log message string.
        """
        return self.render(record)

    def _format_segments(self, record: dict[str, Any]) -> str:
        """Render segment by segment (color markup, and the compiled renderer's
        fallback for a value that rejects its format spec).

        Braces in message content are naturally preserved since
        we don't do any string replacement on the output.
        """
        parts: list[str] = []

        # Only fetch extra if needed
        if self._needs_extra:
            extra = record.get("extra", {})
            if not isinstance(extra, dict):
                extra = {}
        else:
            extra = {}

        # Pre-format thread/process only if needed (avoid string formatting overhead)
        thread_str = (
            f"{record.get('thread_name', '')}:{record.get('thread_id', 0)}"
            if self._needs_thread
            else ""
        )
        process_str = (
            f"{record.get('process_name', '')}:{record.get('process_id', 0)}"
            if self._needs_process
            else ""
        )

        # Styles opened by template markup (only present when colorizing)
        styles: list[str] = []

        for seg in self._segments:
            if isinstance(seg, LiteralSegment):
                parts.append(seg.text)
            elif isinstance(seg, TokenSegment):
                # TokenSegment - get value lazily
                # The message before markup rendering, when it has ANSI codes
                styled_from = None
                if seg.is_extra:
                    value = extra.get(seg.extra_key, "")
                else:
                    key = seg.key
                    if key == "time":
                        value = record.get("timestamp", "")
                    elif key == "level":
                        value = record.get("level", "")
                    elif key == "name" or key == "module":
                        value = record.get("name", "")
                    elif key == "function":
                        value = record.get("function", "")
                    elif key == "line":
                        value = record.get("line", 0)
                    elif key == "file":
                        value = record.get("file", "")
                    elif key == "elapsed":
                        value = record.get("elapsed", "00:00:00.000")
                    elif key == "thread":
                        value = thread_str
                    elif key == "process":
                        value = process_str
                    elif key == "message":
                        message = record.get("message", "")
                        if "<" not in message or "colors" in record:
                            # No markup, or `opt(colors=False)`: the message as is
                            value = message
                        elif styles:
                            # Keep template styles alive across resets in the message markup
                            value = apply_color_markup(message, True, "".join(styles))
                            styled_from = message
                        else:
                            value = apply_color_markup(message, self._colorize)
                            if self._colorize:
                                styled_from = message
                    # Fields added after the ones above: checked last so existing
                    # templates pay nothing for them
                    else:
                        value = self._new_field_value(seg, record)

                if seg.spec:
                    try:
                        if styled_from is not None:
                            # The spec lays out the text without its escape codes
                            plain = apply_color_markup(styled_from, False)
                            text = _format_styled(value, plain, seg.spec)
                        else:
                            text = format(value, seg.spec)
                    except (ValueError, TypeError):
                        text = str(value)
                else:
                    text = str(value)

                if self._colorize and not seg.is_extra and not seg.in_markup:
                    if seg.key == "level":
                        text = colorize_level(text, str(value))
                    elif style := _TOKEN_STYLES.get(seg.key):
                        text = f"{style}{text}{_RESET}"

                parts.append(text)
            elif isinstance(seg, StyleSegment):
                opened = seg.ansi if seg.ansi is not None else level_style(record.get("level", ""))
                styles.append(opened)
                parts.append(opened)
            else:  # StyleEndSegment
                styles.pop()
                parts.append(_RESET)
                parts.extend(styles)

        # Close styles left open by the template
        if styles:
            parts.append(_RESET)

        exception = record.get("exception")
        if exception and not self._has_exception:
            parts.append("\n")
            parts.append(exception)

        return "".join(parts)

    @staticmethod
    def _new_field_value(seg: TokenSegment, record: dict[str, Any]) -> Any:
        """Value of a `{time:<spec>}`, `{level.*}`, `{file.path}`, `{thread.*}`,
        `{process.*}` or `{exception}` token."""
        key = seg.key
        if seg.time_formatter is not None:
            return seg.time_formatter.format_rfc3339(record.get("timestamp", ""))
        if key == "level.no" or key == "level.icon":
            details = level_details(str(record.get("level", "")))
            if details is None:
                return ""
            return details[0] if key == "level.no" else details[1]
        if key == "file.path":
            return record.get("file_path", "")
        if key == "thread.name":
            return record.get("thread_name", "")
        if key == "thread.id":
            return record.get("thread_id", 0)
        if key == "process.name":
            return record.get("process_name", "")
        if key == "process.id":
            return record.get("process_id", 0)
        if key == "exception":
            return record.get("exception") or ""
        if key == _EXTRA_ALL_KEY:
            rendered = record.get("extra_repr")
            if rendered is None:
                rendered = _py_repr_extra(record.get("extra"))
            return rendered
        return ""


# Record lookup for each token of a compiled renderer (``get`` is ``record.get``)
_COMPILED_TOKEN_EXPRS: dict[str, str] = {
    "time": "get('timestamp', '')",
    "level": "get('level', '')",
    "name": "get('name', '')",
    "module": "get('name', '')",
    "function": "get('function', '')",
    "line": "get('line', 0)",
    "file": "get('file', '')",
    "elapsed": "get('elapsed', '00:00:00.000')",
    "thread": "thread_str",
    "process": "process_str",
    "message": "message",
    "level.no": "level_no",
    "level.icon": "level_icon",
    "file.path": "get('file_path', '')",
    "thread.name": "get('thread_name', '')",
    "thread.id": "get('thread_id', 0)",
    "process.name": "get('process_name', '')",
    "process.id": "get('process_id', 0)",
    "exception": "(get('exception') or '')",
    _EXTRA_ALL_KEY: "extra_repr",
}

# Format specs that can be written into an f-string as they are
_PLAIN_SPEC = re.compile(r"[^{}\\'\"\n\r]*")


def _escape_literal(text: str) -> str:
    """``text`` as the literal part of a double-quoted f-string."""
    escaped = text.encode("unicode_escape").decode("ascii").replace('"', '\\"')
    return escaped.replace("{", "{{").replace("}", "}}")


def _compile_renderer(
    segments: tuple[Segment, ...],
    has_exception: bool,
    fallback: Callable[[dict[str, Any]], str],
) -> Callable[[dict[str, Any]], str] | None:
    """Compile ``segments`` into one function rendering the whole template as an f-string.

    The result renders exactly what ``_format_segments`` does for templates
    without color markup, in one pass without the per-segment dispatch. Values
    the record lacks get the same defaults; a value that rejects its format
    spec makes the function defer to ``fallback`` (which falls back per
    segment); ``None`` means the template cannot be compiled (an unusual spec).
    """
    namespace: dict[str, Any] = {
        "apply_color_markup": apply_color_markup,
        "level_details": level_details,
        "_py_repr_extra": _py_repr_extra,
        "fallback": fallback,
    }
    pieces: list[str] = []
    prelude: list[str] = []
    needed: set[str] = set()
    for index, seg in enumerate(segments):
        if isinstance(seg, LiteralSegment):
            pieces.append(_escape_literal(seg.text))
            continue
        if not isinstance(seg, TokenSegment):
            return None
        if seg.spec is not None and _PLAIN_SPEC.fullmatch(seg.spec) is None:
            return None
        if seg.is_extra:
            key_name = f"extra_key_{index}"
            namespace[key_name] = seg.extra_key
            expr = f"extra.get({key_name}, '')"
            needed.add("extra")
        elif seg.time_formatter is not None:
            fmt_name = f"time_formatter_{index}"
            namespace[fmt_name] = seg.time_formatter
            expr = f"{fmt_name}.format_rfc3339(get('timestamp', ''))"
        else:
            token_expr = _COMPILED_TOKEN_EXPRS.get(seg.key)
            if token_expr is None:
                return None
            expr = token_expr
            needed.add(seg.key)
        spec = f":{seg.spec}" if seg.spec else ""
        pieces.append(f"{{{expr}{spec}}}")

    if "extra" in needed:
        prelude.append("extra = get('extra', {})")
        prelude.append("if not isinstance(extra, dict): extra = {}")
    if "thread" in needed:
        prelude.append("thread_str = f\"{get('thread_name', '')}:{get('thread_id', 0)}\"")
    if "process" in needed:
        prelude.append("process_str = f\"{get('process_name', '')}:{get('process_id', 0)}\"")
    if "message" in needed:
        prelude.append("message = get('message', '')")
        # No markup, or `opt(colors=False)`: the message as is
        prelude.append("if '<' in message and 'colors' not in record:")
        prelude.append("    message = apply_color_markup(message, False)")
    if "level.no" in needed or "level.icon" in needed:
        prelude.append("details = level_details(str(get('level', '')))")
        if "level.no" in needed:
            prelude.append("level_no = '' if details is None else details[0]")
        if "level.icon" in needed:
            prelude.append("level_icon = '' if details is None else details[1]")
    if _EXTRA_ALL_KEY in needed:
        prelude.append("extra_repr = get('extra_repr')")
        prelude.append("if extra_repr is None: extra_repr = _py_repr_extra(get('extra'))")

    if not has_exception:
        # The template does not place the exception itself: append it
        epilogue = [
            "exception = get('exception')",
            "return out + '\\n' + exception if exception else out",
        ]
    else:
        epilogue = ["return out"]
    body = [
        "get = record.get",
        *prelude,
        "try:",
        f'    out = f"{"".join(pieces)}"',
        "except (ValueError, TypeError):",
        "    return fallback(record)",
        *epilogue,
    ]
    source = "def render(record):\n" + "".join(f"    {line}\n" for line in body)
    try:
        # The source is built only from the parsed template, never from a record
        exec(source, namespace)
    except SyntaxError:
        return None
    render: Callable[[dict[str, Any]], str] = namespace["render"]
    return render
