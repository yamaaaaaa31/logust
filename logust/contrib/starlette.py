"""Starlette/FastAPI middleware for request logging.

This module provides middleware for automatic request/response logging
in Starlette and FastAPI applications.

Requires: starlette (pip install starlette or pip install fastapi)

Example:
    >>> from fastapi import FastAPI
    >>> from logust.contrib import RequestLoggerMiddleware
    >>>
    >>> app = FastAPI()
    >>> app.add_middleware(RequestLoggerMiddleware)
    >>>
    >>> # All requests are now logged with timing information
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable, Sequence
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, ClassVar

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp
except ImportError as e:
    raise ImportError(
        "Starlette is required for this module. Install it with: pip install starlette"
    ) from e

if TYPE_CHECKING:
    from logust import Logger

_request_id: ContextVar[str] = ContextVar("logust_request_id", default="")


def get_request_id() -> str:
    """Get the current request ID from context.

    Returns:
        The request ID for the current request, or empty string if not in a request.

    Example:
        >>> from logust.contrib.starlette import get_request_id
        >>>
        >>> @app.get("/users/{user_id}")
        >>> async def get_user(user_id: int):
        ...     # Access the current request ID anywhere in your code
        ...     request_id = get_request_id()
        ...     logger.info(f"Processing request {request_id}")
    """
    return _request_id.get()


class RequestLoggerMiddleware(BaseHTTPMiddleware):  # type: ignore[misc]
    """Middleware that logs HTTP requests and responses.

    Features:
    - Automatic request/response timing
    - Client IP detection (supports X-Forwarded-For, X-Real-IP)
    - Request ID generation and propagation via contextvars
    - Configurable route skipping
    - Optional request body logging with sensitive data masking
    - Integration with logust.contextualize for structured logging

    Example:
        >>> from fastapi import FastAPI
        >>> from logust.contrib import RequestLoggerMiddleware
        >>>
        >>> app = FastAPI()
        >>>
        >>> # Basic usage
        >>> app.add_middleware(RequestLoggerMiddleware)
        >>>
        >>> # With configuration
        >>> app.add_middleware(
        ...     RequestLoggerMiddleware,
        ...     skip_routes=["/health", "/metrics"],
        ...     skip_regexes=[r"^/docs", r"^/openapi\\.json$"],
        ...     include_request_body=True,
        ...     max_body_size=1000,
        ...     mask_sensitive_data=True,
        ... )
    """

    _SENSITIVE_KEYS: ClassVar[set[str]] = {
        "password",
        "token",
        "secret",
        "key",
        "authorization",
        "api_key",
        "access_token",
        "refresh_token",
        "jwt",
        "passwd",
        "credential",
    }

    _BODY_METHODS: ClassVar[set[str]] = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(
        self,
        app: ASGIApp,
        *,
        skip_routes: Sequence[str] | None = None,
        skip_regexes: Sequence[str] | None = None,
        include_request_body: bool = False,
        max_body_size: int = 1000,
        mask_sensitive_data: bool = True,
        logger: Logger | None = None,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI application.
            skip_routes: List of route prefixes to skip logging for.
            skip_regexes: List of regex patterns to skip logging for.
            include_request_body: Whether to log request bodies.
            max_body_size: Maximum body size to log (truncates larger bodies).
            mask_sensitive_data: Whether to mask sensitive fields in body.
            logger: Custom logust logger instance. If None, uses default.
        """
        self._skip_routes = set(skip_routes) if skip_routes else set()
        self._skip_regexes = [re.compile(regex) for regex in (skip_regexes or [])]
        self._include_request_body = include_request_body
        self._max_body_size = max_body_size
        self._mask_sensitive_data = mask_sensitive_data
        self._logger = logger
        super().__init__(app)

    @property
    def logger(self) -> Logger:
        """Get the logust logger instance."""
        if self._logger is None:
            from logust import logger

            return logger
        return self._logger

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Process the request and log timing information."""
        if self._should_skip(request):
            return await call_next(request)

        return await self._log_request(request, call_next)

    def _should_skip(self, request: Request) -> bool:
        """Check if this request should skip logging."""
        path = request.url.path

        if any(path.startswith(route) for route in self._skip_routes):
            return True

        return any(regex.match(path) for regex in self._skip_regexes)

    async def _log_request(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Log the request and response with timing."""
        request_id = str(uuid.uuid4())[:8]
        _request_id.set(request_id)

        start_time = time.perf_counter()
        client_ip = self._get_client_ip(request)

        body_log = ""
        if self._include_request_body and request.method in self._BODY_METHODS:
            body_log = await self._get_request_body(request)

        with self.logger.contextualize(request_id=request_id, path=request.url.path):
            self._log_request_start(request, client_ip, body_log)

            try:
                response = await call_next(request)
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                self.logger.error(
                    f"Request failed: {request.method} {request.url.path} "
                    f"error={e.__class__.__name__} time={elapsed:.4f}s ip={client_ip}"
                )
                raise

            elapsed = time.perf_counter() - start_time
            self._log_response(request, response, elapsed, client_ip)

            return response

    def _log_request_start(self, request: Request, client_ip: str, body: str) -> None:
        """Log the start of a request."""
        parts = [
            "Request started:",
            request.method,
            request.url.path,
            f"ip={client_ip}",
        ]

        if request.query_params:
            parts.append(f"query={dict(request.query_params)}")
        if body:
            parts.append(f"body={body}")

        self.logger.info(" ".join(parts))

    def _log_response(
        self,
        request: Request,
        response: Response,
        elapsed: float,
        client_ip: str,
    ) -> None:
        """Log the response."""
        status = "successful" if response.status_code < 400 else "failed"
        message = (
            f"Request {status}: {request.method} {request.url.path} "
            f"status={response.status_code} time={elapsed:.4f}s ip={client_ip}"
        )

        if response.status_code >= 500:
            self.logger.error(message)
        elif response.status_code >= 400:
            self.logger.warning(message)
        else:
            self.logger.info(message)

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract client IP from request headers."""
        headers = request.headers

        forwarded_for: str | None = headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()

        real_ip: str | None = headers.get("x-real-ip")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"

    async def _get_request_body(self, request: Request) -> str:
        """Get and optionally mask the request body."""
        try:
            content_type = request.headers.get("content-type", "")

            if "multipart/form-data" in content_type:
                content_length = request.headers.get("content-length", "unknown")
                return f"<multipart: size={content_length}>"

            body_bytes = await request.body()
            if not body_bytes:
                return ""

            body_str: str
            if len(body_bytes) > self._max_body_size:
                body_str = (
                    body_bytes[: self._max_body_size].decode("utf-8", errors="ignore") + "..."
                )
            else:
                body_str = body_bytes.decode("utf-8", errors="ignore")

            if self._mask_sensitive_data:
                return self._mask_sensitive(body_str)
            return body_str

        except Exception:
            return "<body_error>"

    def _mask_sensitive(self, body: str) -> str:
        """Mask sensitive fields in JSON body."""
        try:
            import json

            data = json.loads(body)
            masked = self._mask_dict(data)
            return json.dumps(masked)
        except (json.JSONDecodeError, TypeError):
            return body

    def _mask_dict(self, obj: Any) -> Any:
        """Recursively mask sensitive fields in a dict."""
        if isinstance(obj, dict):
            return {
                k: "***" if self._is_sensitive_key(k) else self._mask_dict(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [self._mask_dict(item) for item in obj]
        return obj

    def _is_sensitive_key(self, key: str) -> bool:
        """Check if a key name indicates sensitive data."""
        key_lower = key.lower()
        return any(sensitive in key_lower for sensitive in self._SENSITIVE_KEYS)


def setup_fastapi(
    app: Any,
    *,
    skip_routes: Sequence[str] | None = None,
    skip_regexes: Sequence[str] | None = None,
    include_request_body: bool = False,
    intercept_logging: bool = True,
) -> None:
    """One-liner setup for FastAPI applications.

    This function sets up:
    - RequestLoggerMiddleware for request/response logging
    - Standard logging interception (optional)
    - Request ID contextualization

    Args:
        app: FastAPI application instance.
        skip_routes: Routes to skip logging for.
        skip_regexes: Regex patterns to skip logging for.
        include_request_body: Whether to log request bodies.
        intercept_logging: Whether to redirect standard logging to logust.

    Example:
        >>> from fastapi import FastAPI
        >>> from logust.contrib.starlette import setup_fastapi
        >>>
        >>> app = FastAPI()
        >>> setup_fastapi(app, skip_routes=["/health"])
        >>>
        >>> # That's it! Your app now has:
        >>> # - Request/response logging
        >>> # - Standard logging redirected to logust
        >>> # - Request IDs in all log messages
    """
    app.add_middleware(
        RequestLoggerMiddleware,
        skip_routes=skip_routes,
        skip_regexes=skip_regexes,
        include_request_body=include_request_body,
    )

    if intercept_logging:
        from .logging_handler import intercept_logging as do_intercept

        do_intercept()
