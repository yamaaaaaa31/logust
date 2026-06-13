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

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            request: Any = Request()
            request.scope = scope
            request.url = SimpleNamespace(path=scope.get("path", "/"))
            request.method = scope.get("method", "GET")
            request.headers = scope.get("headers", {})
            request.query_params = scope.get("query_params", None)
            request.client = scope.get("client", SimpleNamespace(host="testclient"))

            async def call_next(_req: Any) -> Any:
                return await self.app(scope, receive, send)

            response = await self.dispatch(request, call_next)  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]
            if response is not None and hasattr(response, "body_iterator"):
                async for chunk in response.body_iterator:
                    await send({"type": "http.response.body", "body": chunk, "more_body": True})
                await send({"type": "http.response.body", "body": b"", "more_body": False})

    class Request:
        pass

    class Response:
        status_code = 200

    middleware_base.BaseHTTPMiddleware = BaseHTTPMiddleware  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]
    requests.Request = Request  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]
    responses.Response = Response  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]
    types.ASGIApp = object  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]  # pyright: ignore[reportAttributeAccessIssue]

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
            def __enter__(self_inner: Any) -> None:  # noqa: N805  # pyright: ignore[reportSelfClsParameterName]
                return None

            def __exit__(self_inner: Any, *exc: Any) -> None:  # noqa: N805  # pyright: ignore[reportSelfClsParameterName]
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


def test_request_id_strips_control_chars_and_truncates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_starlette_module(monkeypatch)
    logger = CapturingLogger()
    middleware = module.RequestLoggerMiddleware(object(), logger=logger)
    request = _request(request_id="abc\r\n\x1b[31mforged log\x07def")

    async def call_next(_request: Any) -> Any:
        return SimpleNamespace(status_code=200)

    asyncio.run(middleware._log_request(request, call_next))

    sanitized = logger.contexts[0]["request_id"]
    assert "\n" not in sanitized
    assert "\r" not in sanitized
    assert "\x1b" not in sanitized
    assert "\x07" not in sanitized
    assert sanitized == "abc[31mforgedlogdef"


def test_request_id_falls_back_when_header_is_only_control_chars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_starlette_module(monkeypatch)
    logger = CapturingLogger()
    middleware = module.RequestLoggerMiddleware(object(), logger=logger)
    request = _request(request_id="\r\n\t\x00")

    async def call_next(_request: Any) -> Any:
        return SimpleNamespace(status_code=200)

    asyncio.run(middleware._log_request(request, call_next))

    assigned = logger.contexts[0]["request_id"]
    assert len(assigned) == 8
    assert all(c in "0123456789abcdef" for c in assigned)


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


def test_canonical_event_waits_for_streaming_body(
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
    request = _request(request_id="req-stream")

    streamed: list[bytes] = []

    async def body_iter() -> Any:
        for chunk in (b"a", b"b", b"c"):
            yield chunk

    async def call_next(_request: Any) -> Any:
        return SimpleNamespace(status_code=200, body_iterator=body_iter())

    response = asyncio.run(middleware._log_request(request, call_next))

    assert records == []

    async def drain() -> None:
        async for chunk in response.body_iterator:
            streamed.append(chunk)

    asyncio.run(drain())

    assert streamed == [b"a", b"b", b"c"]
    assert len(records) == 1
    extra = records[0]["extra"]
    assert extra["status_code"] == "200"
    assert extra["outcome"] == "success"


def test_canonical_event_records_streaming_body_failure(
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
    request = _request(request_id="req-stream-error")

    async def body_iter() -> Any:
        yield b"first"
        raise RuntimeError("stream boom")

    async def call_next(_request: Any) -> Any:
        return SimpleNamespace(status_code=200, body_iterator=body_iter())

    response = asyncio.run(middleware._log_request(request, call_next))
    assert records == []

    async def drain() -> None:
        async for _ in response.body_iterator:
            pass

    with pytest.raises(RuntimeError, match="stream boom"):
        asyncio.run(drain())

    assert len(records) == 1
    extra = records[0]["extra"]
    assert extra["outcome"] == "error"
    assert extra["error.type"] == "RuntimeError"


def test_call_path_classifies_inner_app_failure_after_streaming_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate Starlette's BaseHTTPMiddleware where the inner ASGI app
    raises after the response start has been sent — exercises the
    ``__call__`` override that finalizes the canonical event using the
    ``app_exc`` re-raised after dispatch returns."""
    module = _load_starlette_module(monkeypatch)
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.disable()
    records: list[dict[str, Any]] = []
    logger.add_callback(records.append, level=LogLevel.Trace)

    async def inner_app(scope: Any, receive: Any, send: Any) -> Any:
        async def empty_iter() -> Any:
            if False:
                yield b""

        return SimpleNamespace(status_code=200, body_iterator=empty_iter())

    middleware = module.RequestLoggerMiddleware(
        inner_app, logger=logger, canonical=True, sample_rate=1.0
    )

    async def receive() -> Any:
        return {"type": "http.disconnect"}

    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/items",
        "headers": {},
        "query_params": None,
        "client": SimpleNamespace(host="127.0.0.1"),
    }

    boom = RuntimeError("inner app boom after start")

    real_super_call = module.RequestLoggerMiddleware.__mro__[1].__call__

    async def super_call_with_app_exc(self: Any, s: Any, r: Any, sd: Any) -> None:
        await real_super_call(self, s, r, sd)
        raise boom

    monkeypatch.setattr(
        module.RequestLoggerMiddleware.__mro__[1], "__call__", super_call_with_app_exc
    )

    with pytest.raises(RuntimeError, match="inner app boom after start"):
        asyncio.run(middleware(scope, receive, send))

    assert len(records) == 1
    extra = records[0]["extra"]
    assert extra["outcome"] == "error"
    assert extra["error.type"] == "RuntimeError"


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
