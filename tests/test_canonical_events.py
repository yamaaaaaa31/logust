"""Tests for canonical request events and tail sampling."""

from __future__ import annotations

import asyncio
import importlib
import sys
from contextlib import contextmanager
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from logust.contrib.events import (
    TailSampler,
    add_event_fields,
    canonical_event,
    get_current_event,
    get_event_fields,
)


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


class QueryParams:
    def __init__(self, items: list[tuple[str, str]]) -> None:
        self._items = items

    def __bool__(self) -> bool:
        return bool(self._items)

    def multi_items(self) -> list[tuple[str, str]]:
        return self._items


class CapturingLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, Any]]] = []

    @contextmanager
    def contextualize(self, **_kwargs: Any) -> Any:
        yield self

    def info(self, message: str, **kwargs: Any) -> None:
        self.records.append(("info", message, dict(kwargs)))

    def warning(self, message: str, **kwargs: Any) -> None:
        self.records.append(("warning", message, dict(kwargs)))

    def error(self, message: str, **kwargs: Any) -> None:
        self.records.append(("error", message, dict(kwargs)))


def _request(
    path: str = "/users/123",
    status_path: str = "/users/{user_id}",
    *,
    request_id: str | None = "req-incoming",
) -> Any:
    headers = {
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        "user-agent": "test-client",
    }
    if request_id is not None:
        headers["x-request-id"] = request_id

    return SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path=path),
        headers=headers,
        query_params=QueryParams([("page", "1"), ("access_token", "secret")]),
        client=SimpleNamespace(host="127.0.0.1"),
        scope={"route": SimpleNamespace(path=status_path)},
    )


def test_canonical_event_context_helpers() -> None:
    assert add_event_fields(user_id="outside") is False

    with canonical_event({"event": "job"}) as event:
        assert add_event_fields({"user.id": "u1"}, attempt=2) is True
        assert event["user.id"] == "u1"
        assert get_event_fields()["attempt"] == 2
        assert get_current_event() is event

    assert get_current_event() is None


def test_tail_sampler_keeps_errors_and_slow_events() -> None:
    sampler = TailSampler(rate=0.0, slow_ms=100.0)

    assert sampler.should_keep({"status_code": 200, "duration_ms": 99.0}) is False
    assert sampler.should_keep({"status_code": 500, "duration_ms": 1.0}) is True
    assert sampler.should_keep({"status_code": 200, "duration_ms": 100.0}) is True


def test_tail_sampler_uses_probabilistic_rate() -> None:
    keep = TailSampler(rate=0.5, always_keep_errors=False, random_fn=lambda: 0.4)
    drop = TailSampler(rate=0.5, always_keep_errors=False, random_fn=lambda: 0.6)

    assert keep.should_keep({"status_code": 200}) is True
    assert drop.should_keep({"status_code": 200}) is False


def test_tail_sampler_validates_configuration() -> None:
    with pytest.raises(ValueError, match="rate"):
        TailSampler(rate=-0.1)
    with pytest.raises(ValueError, match="rate"):
        TailSampler(rate=1.1)
    with pytest.raises(ValueError, match="slow_ms"):
        TailSampler(slow_ms=-1)
    with pytest.raises(TypeError, match="keep_if"):
        TailSampler(keep_if=True)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]  # pyright: ignore[reportArgumentType]
    with pytest.raises(TypeError, match="random_fn"):
        TailSampler(random_fn=True)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]  # pyright: ignore[reportArgumentType]


def test_canonical_middleware_emits_single_wide_event(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_starlette_module(monkeypatch)
    logger = CapturingLogger()
    middleware = module.RequestLoggerMiddleware(
        object(),
        logger=logger,
        canonical=True,
    )
    request = _request()

    async def call_next(_request: Any) -> Any:
        assert module.get_request_id() == "req-incoming"
        add_event_fields({"user.id": "user-1"}, user_plan="pro")
        return SimpleNamespace(status_code=201)

    response = asyncio.run(middleware._log_request(request, call_next))

    assert response.status_code == 201
    assert module.get_request_id() == ""
    assert len(logger.records) == 1

    level, message, event = logger.records[0]
    assert level == "info"
    assert message == "http.request"
    assert event["event"] == "http.request"
    assert event["request_id"] == "req-incoming"
    assert event["method"] == "GET"
    assert event["path"] == "/users/123"
    assert event["route"] == "/users/{user_id}"
    assert event["status_code"] == 201
    assert event["outcome"] == "success"
    assert event["client_ip"] == "127.0.0.1"
    assert event["user_agent"] == "test-client"
    assert event["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert event["span_id"] == "00f067aa0ba902b7"
    assert event["user.id"] == "user-1"
    assert event["user_plan"] == "pro"
    assert event["query"] == {"page": "1", "access_token": "***"}
    assert "duration_ms" in event


def test_canonical_middleware_generates_short_request_id_when_header_missing(
    monkeypatch: Any,
) -> None:
    module = _load_starlette_module(monkeypatch)

    logger = CapturingLogger()
    middleware = module.RequestLoggerMiddleware(
        object(),
        logger=logger,
        canonical=True,
    )
    request = _request(request_id=None)

    async def call_next(_request: Any) -> Any:
        generated = module.get_request_id()
        assert len(generated) == 8
        assert all(c in "0123456789abcdef" for c in generated)
        return SimpleNamespace(status_code=200)

    asyncio.run(middleware._log_request(request, call_next))

    event = logger.records[0][2]
    assert len(event["request_id"]) == 8
    assert all(c in "0123456789abcdef" for c in event["request_id"])


def test_canonical_middleware_uses_custom_sampler_predicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_starlette_module(monkeypatch)
    logger = CapturingLogger()
    middleware = module.RequestLoggerMiddleware(
        object(),
        logger=logger,
        canonical=True,
        sample_rate=-1.0,
        sampler=lambda event: event["path"] == "/keep",
    )

    async def call_next(_request: Any) -> Any:
        return SimpleNamespace(status_code=200)

    asyncio.run(middleware._log_request(_request("/drop", "/drop"), call_next))
    assert logger.records == []

    asyncio.run(middleware._log_request(_request("/keep", "/keep"), call_next))
    assert len(logger.records) == 1
    assert logger.records[0][2]["path"] == "/keep"


def test_canonical_middleware_validates_api_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_starlette_module(monkeypatch)

    with pytest.raises(ValueError, match=r"sample_rate|rate"):
        module.RequestLoggerMiddleware(object(), canonical=True, sample_rate=1.1)
    with pytest.raises(ValueError, match="slow_ms"):
        module.RequestLoggerMiddleware(object(), canonical=True, slow_ms=-1)
    with pytest.raises(ValueError, match="max_body_size"):
        module.RequestLoggerMiddleware(object(), max_body_size=-1)
    with pytest.raises(TypeError, match="sampler"):
        module.RequestLoggerMiddleware(object(), canonical=True, sampler=object())


def test_canonical_sampling_drops_normal_events_but_keeps_500s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_starlette_module(monkeypatch)
    logger = CapturingLogger()
    middleware = module.RequestLoggerMiddleware(
        object(),
        logger=logger,
        canonical=True,
        sample_rate=0.0,
    )

    async def ok_call_next(_request: Any) -> Any:
        return SimpleNamespace(status_code=200)

    asyncio.run(middleware._log_request(_request("/ok", "/ok"), ok_call_next))
    assert logger.records == []

    async def failing_call_next(_request: Any) -> Any:
        return SimpleNamespace(status_code=500)

    asyncio.run(middleware._log_request(_request("/fail", "/fail"), failing_call_next))
    assert len(logger.records) == 1
    assert logger.records[0][0] == "error"
    assert logger.records[0][2]["status_code"] == 500
