"""Canonical event helpers for request-scoped structured logging."""

from __future__ import annotations

import random
from collections.abc import Callable, Generator, Mapping, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

_current_event_fields: ContextVar[dict[str, Any] | None] = ContextVar(
    "logust_current_event_fields",
    default=None,
)


@contextmanager
def canonical_event(
    fields: Mapping[str, Any] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Create a request-local canonical event field bag.

    The yielded dictionary is shared with :func:`add_event_fields` for the
    lifetime of the context. Nested contexts restore the previous event.
    """
    event_fields = dict(fields or {})
    token = _current_event_fields.set(event_fields)
    try:
        yield event_fields
    finally:
        _current_event_fields.reset(token)


def get_event_fields() -> dict[str, Any]:
    """Return a copy of the current canonical event fields."""
    fields = _current_event_fields.get()
    return dict(fields or {})


def get_current_event() -> MutableMapping[str, Any] | None:
    """Return the active canonical event mapping, if one exists."""
    return _current_event_fields.get()


def add_event_fields(fields: Mapping[str, Any] | None = None, **kwargs: Any) -> bool:
    """Add fields to the active canonical event.

    Returns ``True`` when a canonical event is active and was updated. Outside
    an active event context this is a no-op and returns ``False``.
    """
    event_fields = _current_event_fields.get()
    if event_fields is None:
        return False

    if fields:
        event_fields.update(fields)
    if kwargs:
        event_fields.update(kwargs)
    return True


def clear_event_fields() -> bool:
    """Clear the active canonical event fields."""
    event_fields = _current_event_fields.get()
    if event_fields is None:
        return False
    event_fields.clear()
    return True


@dataclass(frozen=True, slots=True)
class TailSampler:
    """Decide whether a completed canonical event should be emitted.

    The sampler keeps high-value events first, then applies probabilistic
    sampling to normal traffic.
    """

    rate: float = 1.0
    always_keep_errors: bool = True
    slow_ms: float | None = None
    keep_if: Callable[[Mapping[str, Any]], bool] | None = None
    random_fn: Callable[[], float] = random.random

    def __post_init__(self) -> None:
        """Validate sampler configuration early."""
        if not 0.0 <= self.rate <= 1.0:
            raise ValueError("TailSampler rate must be between 0.0 and 1.0")
        if self.slow_ms is not None and self.slow_ms < 0:
            raise ValueError("TailSampler slow_ms must be greater than or equal to 0")
        if self.keep_if is not None and not callable(self.keep_if):
            raise TypeError("TailSampler keep_if must be callable")
        if not callable(self.random_fn):
            raise TypeError("TailSampler random_fn must be callable")

    def should_keep(self, event: Mapping[str, Any]) -> bool:
        """Return ``True`` if the event should be logged."""
        if self.keep_if is not None and self.keep_if(event):
            return True

        if self.always_keep_errors and _is_error_event(event):
            return True

        if self.slow_ms is not None and _duration_ms(event) >= self.slow_ms:
            return True

        if self.rate >= 1.0:
            return True
        if self.rate <= 0.0:
            return False
        return self.random_fn() < self.rate


def _is_error_event(event: Mapping[str, Any]) -> bool:
    status = event.get("status_code")
    if isinstance(status, int) and status >= 500:
        return True
    if isinstance(status, str):
        try:
            if int(status) >= 500:
                return True
        except ValueError:
            pass
    return event.get("outcome") == "error" or "error.type" in event


def _duration_ms(event: Mapping[str, Any]) -> float:
    value = event.get("duration_ms")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0
