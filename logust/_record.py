"""loguru-compatible values used in the record dict passed to filters, patchers
and ``add_callback`` callbacks.

The string-like values subclass ``str`` so existing logust code that treats
``record["level"]`` or ``record["file"]`` as plain strings keeps working, while
ported loguru code can use ``record["level"].no``, ``record["file"].path`` and
so on. Instances are created by the Rust core and cached, so they are shared
between records: treat them as read-only.
"""

from __future__ import annotations

import datetime
from typing import Any

__all__ = [
    "RecordElapsed",
    "RecordFile",
    "RecordLevelStr",
    "RecordProcess",
    "RecordThread",
]


class RecordLevelStr(str):
    """Level name (a ``str``) that also exposes loguru's ``.name``, ``.no`` and ``.icon``.

    ``record["level"] == "INFO"`` keeps working, and ported loguru filters such
    as ``record["level"].no >= 30`` work too.
    """

    name: str
    no: int
    icon: str

    def __new__(cls, name: str, no: int, icon: str = "") -> RecordLevelStr:
        self = super().__new__(cls, name)
        self.name = str(name)
        self.no = no
        self.icon = icon
        return self

    def __getnewargs__(self) -> tuple[Any, ...]:
        return (self.name, self.no, self.icon)


class RecordFile(str):
    """Source file basename (a ``str``) that also exposes loguru's ``.name`` and ``.path``."""

    name: str
    path: str

    def __new__(cls, name: str, path: str) -> RecordFile:
        self = super().__new__(cls, name)
        self.name = str(name)
        self.path = path
        return self

    def __getnewargs__(self) -> tuple[Any, ...]:
        return (self.name, self.path)


class RecordThread:
    """Thread information with loguru's ``.id`` and ``.name`` attributes."""

    __slots__ = ("id", "name")

    def __init__(self, id: int, name: str) -> None:
        self.id = id
        self.name = name

    def __repr__(self) -> str:
        return f"(id={self.id!r}, name={self.name!r})"

    def __format__(self, spec: str) -> str:
        return format(self.id, spec)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RecordThread):
            return self.id == other.id and self.name == other.name
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.id, self.name))


class RecordProcess:
    """Process information with loguru's ``.id`` and ``.name`` attributes."""

    __slots__ = ("id", "name")

    def __init__(self, id: int, name: str) -> None:
        self.id = id
        self.name = name

    def __repr__(self) -> str:
        return f"(id={self.id!r}, name={self.name!r})"

    def __format__(self, spec: str) -> str:
        return format(self.id, spec)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RecordProcess):
            return self.id == other.id and self.name == other.name
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.id, self.name))


class RecordElapsed(datetime.timedelta):
    """Time since logger start: a ``timedelta`` whose ``str()`` is logust's
    ``HH:MM:SS.mmm`` form (the value ``{elapsed}`` renders)."""

    __slots__ = ()

    def __str__(self) -> str:
        total_ms = max(0, (self.days * 86400 + self.seconds) * 1000 + self.microseconds // 1000)
        secs, ms = divmod(total_ms, 1000)
        hours, rem = divmod(secs, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}.{ms:03}"

    def __format__(self, spec: str) -> str:
        return format(str(self), spec)
