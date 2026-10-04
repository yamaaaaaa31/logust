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
    colorize_level,
    level_details,
    level_style,
    split_format_markup,
)

if TYPE_CHECKING:
    pass

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
    )

    # Token pattern: {token} or {token:spec} or {extra[key]} or {extra[key]:spec}
    # Only matches known tokens to preserve unknown patterns as literals
    # extra[...] allows any characters except ] (supports hyphens, dots, unicode, etc.)
    # Built from KNOWN_TOKENS to ensure consistency with auto-detect
    _TOKEN_PATTERN = re.compile(
        r"\{(" + "|".join(re.escape(t) for t in KNOWN_TOKENS) + r"|extra\[[^\]]+\])(?::([^}]*))?\}"
    )

    def __init__(self, template: str, colorize: bool = False) -> None:
        """Parse the template into segments.

        Args:
            template: Format template string.
            colorize: Style tokens and render message markup as ANSI codes.
        """
        self._colorize = colorize
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

            if key.startswith("extra["):
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
        message, nested extra, file path. Must match ``src/lib.rs``
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
        """Format the record using pre-parsed template.

        Single-pass formatting using pre-parsed segments.
        Braces in message content are naturally preserved since
        we don't do any string replacement on the output.

        Args:
            record: Log record dictionary.

        Returns:
            Formatted log message string.
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
                        if styles:
                            # Keep template styles alive across resets in the message markup
                            value = apply_color_markup(message, True, "".join(styles))
                        else:
                            value = apply_color_markup(message, self._colorize)
                    # Fields added after the ones above: checked last so existing
                    # templates pay nothing for them
                    else:
                        value = self._new_field_value(seg, record)

                if seg.spec:
                    try:
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
        return ""
