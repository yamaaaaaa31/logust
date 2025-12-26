"""Pre-parsed template for callable sinks.

Provides efficient single-pass formatting by parsing the template once
at sink creation time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


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


# Type alias for segment types
Segment = LiteralSegment | TokenSegment


class ParsedCallableTemplate:
    """Pre-parsed format template for callable sinks.

    Parses the template once at creation time and provides efficient
    single-pass formatting. This avoids the overhead of multiple
    .replace() calls and repeated regex matching.

    Performance improvement: ~1-2us/log for callable sinks.
    """

    __slots__ = ("_segments",)

    # Token pattern: {token} or {token:spec} or {extra[key]} or {extra[key]:spec}
    # Only matches known tokens to preserve unknown patterns as literals
    _TOKEN_PATTERN = re.compile(
        r"\{(time|level|name|module|function|line|file|"
        r"elapsed|thread|process|message|extra\[\w+\])(?::([^}]+))?\}"
    )

    def __init__(self, template: str) -> None:
        """Parse the template into segments.

        Args:
            template: Format template string.
        """
        self._segments: tuple[Segment, ...] = self._parse(template)

    def _parse(self, template: str) -> tuple[Segment, ...]:
        """Parse template into literal and token segments.

        Args:
            template: Format template string.

        Returns:
            Tuple of segments (immutable for performance).
        """
        segments: list[Segment] = []
        last_end = 0

        for match in self._TOKEN_PATTERN.finditer(template):
            # Add literal before this match
            if match.start() > last_end:
                segments.append(LiteralSegment(template[last_end : match.start()]))

            key = match.group(1)
            spec = match.group(2)

            if key.startswith("extra["):
                extra_key = key[6:-1]  # Extract key from extra[key]
                segments.append(TokenSegment("extra", spec, True, extra_key))
            else:
                segments.append(TokenSegment(key, spec, False, None))

            last_end = match.end()

        # Add remaining literal
        if last_end < len(template):
            segments.append(LiteralSegment(template[last_end:]))

        return tuple(segments)

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
        extra = record.get("extra", {})
        if not isinstance(extra, dict):
            extra = {}

        # Build token values lazily from record
        # Note: thread and process are formatted as "name:id"
        token_values: dict[str, Any] = {
            "time": record.get("timestamp", ""),
            "level": record.get("level", ""),
            "name": record.get("name", ""),
            "module": record.get("name", ""),  # module is alias for name
            "function": record.get("function", ""),
            "line": record.get("line", 0),
            "file": record.get("file", ""),
            "elapsed": record.get("elapsed", "00:00:00.000"),
            "thread": f"{record.get('thread_name', '')}:{record.get('thread_id', 0)}",
            "process": f"{record.get('process_name', '')}:{record.get('process_id', 0)}",
            "message": record.get("message", ""),
        }

        for seg in self._segments:
            if isinstance(seg, LiteralSegment):
                parts.append(seg.text)
            else:
                # TokenSegment
                if seg.is_extra:
                    value = extra.get(seg.extra_key, "")
                else:
                    value = token_values.get(seg.key, "")

                if seg.spec:
                    try:
                        parts.append(format(value, seg.spec))
                    except (ValueError, TypeError):
                        parts.append(str(value))
                else:
                    parts.append(str(value))

        return "".join(parts)
