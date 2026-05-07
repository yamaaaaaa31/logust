"""Logust contrib - utilities and integrations for common use cases.

This module provides zero-config utilities that make logust even easier to use:

- InterceptHandler: Redirect standard logging to logust
- log_fn / debug_fn: Function timing decorators
- add_event_fields / TailSampler: Canonical event helpers
- Starlette/FastAPI middleware (optional)

Example:
    >>> from logust.contrib import intercept_logging, log_fn
    >>>
    >>> # Redirect all standard logging to logust
    >>> intercept_logging()
    >>>
    >>> # Time function execution
    >>> @log_fn
    ... def my_function():
    ...     pass
"""

from __future__ import annotations

from .decorators import debug_fn, log_fn
from .events import (
    TailSampler,
    add_event_fields,
    canonical_event,
    clear_event_fields,
    get_current_event,
    get_event_fields,
)
from .logging_handler import InterceptHandler, intercept_logging

__all__ = [
    "InterceptHandler",
    "TailSampler",
    "add_event_fields",
    "canonical_event",
    "clear_event_fields",
    "debug_fn",
    "get_current_event",
    "get_event_fields",
    "intercept_logging",
    "log_fn",
]

try:
    from .starlette import RequestLoggerMiddleware as RequestLoggerMiddleware
    from .starlette import get_request_id as get_request_id
    from .starlette import setup_fastapi as setup_fastapi

    __all__.extend(["RequestLoggerMiddleware", "get_request_id", "setup_fastapi"])
except ImportError:
    pass
