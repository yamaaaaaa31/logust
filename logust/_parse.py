"""Log file parsing utilities."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def parse(
    file: str | Path,
    pattern: str,
    *,
    cast: dict[str, type] | None = None,
    chunk_size: int = 8192,
) -> Iterator[dict[str, Any]]:
    """Parse a log file and extract structured data.

    Uses regex named groups to extract fields from each log line.
    Lines that don't match the pattern are skipped.

    Args:
        file: Path to the log file.
        pattern: Regex pattern with named groups (e.g., "(?P<level>\\S+)").
        cast: Optional dict mapping group names to types for conversion.
        chunk_size: Read buffer size in bytes.

    Yields:
        Dict containing the matched groups for each line.

    Examples:
        >>> # Basic parsing
        >>> pattern = r"(?P<time>\\S+) \\| (?P<level>\\S+) \\| (?P<message>.*)"
        >>> for record in parse("app.log", pattern):
        ...     print(record["time"], record["level"], record["message"])

        >>> # With type casting
        >>> pattern = r"(?P<timestamp>\\d+) (?P<level>\\w+) (?P<count>\\d+)"
        >>> for record in parse("app.log", pattern, cast={"count": int}):
        ...     print(record["count"] + 1)  # count is now an int

        >>> # Parse JSON logs
        >>> import json
        >>> for line in open("app.json"):
        ...     record = json.loads(line)
        ...     # Process record

        >>> # Default logust format
        >>> pattern = r"(?P<time>[\\d-]+ [\\d:.]+) \\| (?P<level>\\w+)\\s+\\| (?P<message>.*)"
        >>> for record in parse("app.log", pattern):
        ...     if record["level"] == "ERROR":
        ...         print(record["message"])
    """
    compiled = re.compile(pattern)
    cast = cast or {}
    file_path = Path(file)

    with file_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n\r")
            match = compiled.match(line)
            if match:
                record = match.groupdict()
                for key, type_func in cast.items():
                    if key in record and record[key] is not None:
                        try:
                            record[key] = type_func(record[key])
                        except (ValueError, TypeError):
                            pass
                yield record


def parse_json(
    file: str | Path,
    *,
    strict: bool = False,
) -> Iterator[dict[str, Any]]:
    """Parse a JSON-lines log file.

    Each line is expected to be a valid JSON object.

    Args:
        file: Path to the log file.
        strict: If True, raise an exception on invalid JSON.
                If False, skip invalid lines.

    Yields:
        Dict containing the parsed JSON for each line.

    Examples:
        >>> for record in parse_json("app.json"):
        ...     print(record["level"], record["message"])

        >>> # Filter by level
        >>> errors = [r for r in parse_json("app.json") if r.get("level") == "ERROR"]
    """
    import json

    file_path = Path(file)

    with file_path.open("r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                if strict:
                    raise ValueError(f"Invalid JSON at line {line_num}: {e}") from e
