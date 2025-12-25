"""Intercept standard logging and redirect to logust.

This module provides a handler that captures all standard library logging
calls and redirects them to logust, giving you consistent log formatting
and the performance benefits of logust's Rust core.

Example:
    >>> from logust.contrib import intercept_logging
    >>>
    >>> # One-liner setup - redirects ALL logging to logust
    >>> intercept_logging()
    >>>
    >>> # Now standard logging goes through logust
    >>> import logging
    >>> logging.info("This goes through logust!")
    >>>
    >>> # Third-party libraries automatically use logust
    >>> import requests  # Their logs now go through logust too
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logust import Logger


class InterceptHandler(logging.Handler):
    """A logging handler that redirects standard logging to logust.

    This handler intercepts log records from Python's standard logging
    module and forwards them to logust, preserving the original logger
    name, function, and line number information.

    Example:
        >>> import logging
        >>> from logust.contrib import InterceptHandler
        >>>
        >>> # Manual setup
        >>> logging.root.handlers = [InterceptHandler()]
        >>> logging.root.setLevel(logging.DEBUG)
        >>>
        >>> # Or use the convenience function
        >>> from logust.contrib import intercept_logging
        >>> intercept_logging()
    """

    def __init__(self, target: Logger | None = None) -> None:
        """Initialize the handler.

        Args:
            target: Target logust logger. If None, uses the default logger.
        """
        super().__init__()
        self._target = target

    @property
    def target(self) -> Logger:
        """Get the target logust logger."""
        if self._target is None:
            from logust import logger

            return logger
        return self._target

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to logust.

        Args:
            record: The log record from standard logging.
        """
        level: str | int = record.levelname

        exception = None
        if record.exc_info:
            import traceback

            exception = "".join(traceback.format_exception(*record.exc_info))

        self.target._inner.log(
            level,
            record.getMessage(),
            exception=exception,
        )


def intercept_logging(
    level: int = logging.DEBUG,
    target: Logger | None = None,
) -> None:
    """Redirect all standard logging to logust.

    This is a convenience function that sets up InterceptHandler to capture
    all logging from the standard library and third-party packages.

    Args:
        level: Minimum level to capture (default: DEBUG, captures everything).
        target: Target logust logger. If None, uses the default logger.

    Example:
        >>> from logust.contrib import intercept_logging
        >>>
        >>> # Redirect all logging to logust
        >>> intercept_logging()
        >>>
        >>> # Now all standard logging goes through logust
        >>> import logging
        >>> logging.warning("This appears in logust format!")
        >>>
        >>> # Third-party library logs also go through logust
        >>> import urllib3
        >>> # urllib3's logs now appear in logust format
    """
    logging.root.handlers = [InterceptHandler(target)]
    logging.root.setLevel(level)

    for name in logging.root.manager.loggerDict:
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
