"""Security regression tests for Starlette request logging."""

from __future__ import annotations

import asyncio
import importlib
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, ClassVar

import pytest


def _load_starlette_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Load the Starlette integration with lightweight dependency stubs."""
    starlette = ModuleType("starlette")
    middleware = ModuleType("starlette.middleware")
    middleware_base = ModuleType("starlette.middleware.base")
    requests = ModuleType("starlette.requests")
    responses = ModuleType("starlette.responses")
    types = ModuleType("starlette.types")

    class BaseHTTPMiddleware:
        def __init__(self, app: Any) -> None:
            self.app = app

    class Request:
        pass

    class Response:
        status_code = 200

    middleware_base.BaseHTTPMiddleware = BaseHTTPMiddleware
    requests.Request = Request
    responses.Response = Response
    types.ASGIApp = object

    monkeypatch.setitem(sys.modules, "starlette", starlette)
    monkeypatch.setitem(sys.modules, "starlette.middleware", middleware)
    monkeypatch.setitem(sys.modules, "starlette.middleware.base", middleware_base)
    monkeypatch.setitem(sys.modules, "starlette.requests", requests)
    monkeypatch.setitem(sys.modules, "starlette.responses", responses)
    monkeypatch.setitem(sys.modules, "starlette.types", types)
    sys.modules.pop("logust.contrib.starlette", None)
    return importlib.import_module("logust.contrib.starlette")


class CapturingLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


class QueryParams:
    def __init__(self, items: list[tuple[str, str]]) -> None:
        self._items = items

    def __bool__(self) -> bool:
        return bool(self._items)

    def multi_items(self) -> list[tuple[str, str]]:
        return self._items


def _middleware(module: ModuleType, *, max_body_size: int = 1000) -> Any:
    middleware = module.RequestLoggerMiddleware.__new__(module.RequestLoggerMiddleware)
    middleware._max_body_size = max_body_size
    middleware._mask_sensitive_data = True
    middleware._logger = CapturingLogger()
    return middleware


def test_request_logger_masks_sensitive_query_params(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_starlette_module(monkeypatch)
    middleware = _middleware(module)
    request = SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path="/callback"),
        query_params=QueryParams(
            [
                ("access_token", "SECRET_TOKEN"),
                ("page", "1"),
                ("password", "SECRET_PASSWORD"),
            ]
        ),
    )

    middleware._log_request_start(request, "127.0.0.1", "")

    message = middleware._logger.messages[0]
    assert "SECRET_TOKEN" not in message
    assert "SECRET_PASSWORD" not in message
    assert "'access_token': '***'" in message
    assert "'password': '***'" in message
    assert "'page': '1'" in message


def test_request_logger_masks_body_before_truncating_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_starlette_module(monkeypatch)
    middleware = _middleware(module, max_body_size=80)

    class Request:
        headers: ClassVar[dict[str, str]] = {"content-type": "application/json"}

        async def body(self) -> bytes:
            return b'{"password":"SECRET_PASSWORD","padding":"' + (b"A" * 200) + b'"}'

    body = asyncio.run(middleware._get_request_body(Request()))

    assert "SECRET_PASSWORD" not in body
    assert '"password": "***"' in body
    assert body.endswith("...")
