"""Tests for RequestLoggerMiddleware general behavior."""

from __future__ import annotations

import asyncio
import importlib
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from logust._logger import Logger
from logust._logust import LogLevel, PyLogger


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
        self.records: list[tuple[str, str]] = []
        self.contexts: list[dict[str, Any]] = []

    def info(self, message: str) -> None:
        self.records.append(("info", message))

    def warning(self, message: str) -> None:
        self.records.append(("warning", message))

    def error(self, message: str) -> None:
        self.records.append(("error", message))

    def contextualize(self, **kwargs: Any) -> Any:
        self.contexts.append(kwargs)

        class _Ctx:
            def __enter__(self_inner: Any) -> None:
                return None

            def __exit__(self_inner: Any, *exc: Any) -> None:
                return None

        return _Ctx()


def _request(*, request_id: str | None) -> SimpleNamespace:
    headers: dict[str, str] = {}
    if request_id is not None:
        headers["x-request-id"] = request_id
    return SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path="/items"),
        headers=headers,
        query_params=None,
        client=SimpleNamespace(host="127.0.0.1"),
    )


def test_request_id_uses_incoming_header_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_starlette_module(monkeypatch)
    logger = CapturingLogger()
    middleware = module.RequestLoggerMiddleware(object(), logger=logger)
    request = _request(request_id="upstream-id-1234")

    async def call_next(_request: Any) -> Any:
        assert module.get_request_id() == "upstream-id-1234"
        return SimpleNamespace(status_code=200)

    asyncio.run(middleware._log_request(request, call_next))

    assert logger.contexts[0]["request_id"] == "upstream-id-1234"


def test_request_id_falls_back_to_short_uuid_without_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_starlette_module(monkeypatch)
    logger = CapturingLogger()
    middleware = module.RequestLoggerMiddleware(object(), logger=logger)
    request = _request(request_id=None)

    async def call_next(_request: Any) -> Any:
        return SimpleNamespace(status_code=200)

    asyncio.run(middleware._log_request(request, call_next))

    assigned = logger.contexts[0]["request_id"]
    assert len(assigned) == 8
    assert all(c in "0123456789abcdef" for c in assigned)


def test_response_log_keeps_request_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_starlette_module(monkeypatch)
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    records: list[dict[str, Any]] = []
    logger.add_callback(records.append, level=LogLevel.Trace)
    middleware = module.RequestLoggerMiddleware(object(), logger=logger)
    request = _request(request_id="req-abc")

    async def call_next(_request: Any) -> Any:
        return SimpleNamespace(status_code=201)

    asyncio.run(middleware._log_request(request, call_next))

    response_record = next(
        record for record in records if record["message"].startswith("Request successful:")
    )
    assert response_record["extra"]["request_id"] == "req-abc"
    assert response_record["extra"]["path"] == "/items"


def test_canonical_event_with_reserved_keys_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_starlette_module(monkeypatch)
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    records: list[dict[str, Any]] = []
    logger.add_callback(records.append, level=LogLevel.Trace)
    middleware = module.RequestLoggerMiddleware(
        object(), logger=logger, canonical=True, sample_rate=1.0
    )

    event = {
        "method": "GET",
        "path": "/items",
        "status_code": 200,
        "outcome": "success",
        "message": "user-supplied",
        "exception": "user-supplied-exc",
        "_depth": 99,
    }

    middleware._emit_canonical_event(event)

    assert len(records) == 1
    extra = records[0]["extra"]
    assert "message" not in extra
    assert "exception" not in extra
    assert "_depth" not in extra
    assert extra["method"] == "GET"
    assert extra["path"] == "/items"


def test_max_body_size_rejects_negative_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_starlette_module(monkeypatch)
    with pytest.raises(ValueError, match="max_body_size"):
        module.RequestLoggerMiddleware(object(), max_body_size=-1)
