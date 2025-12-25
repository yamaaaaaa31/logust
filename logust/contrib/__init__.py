"""Logust contrib - utilities and integrations for common use cases.

This module provides zero-config utilities that make logust even easier to use:

- InterceptHandler: Redirect standard logging to logust
- log_fn / debug_fn: Function timing decorators
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
from .logging_handler import InterceptHandler, intercept_logging

__all__ = [
    "InterceptHandler",
    "debug_fn",
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
