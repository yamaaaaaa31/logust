"""Real FastAPI/Starlette integration tests for request logging middleware."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("starlette")

from fastapi import FastAPI
from fastapi.testclient import TestClient as FastAPITestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient as StarletteTestClient

from logust.contrib import add_event_fields
from logust.contrib.starlette import RequestLoggerMiddleware, get_request_id


class CapturingLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, Any]]] = []
        self.contexts: list[dict[str, Any]] = []

    @contextmanager
    def contextualize(self, **kwargs: Any) -> Any:
        self.contexts.append(dict(kwargs))
        yield self

    def info(self, message: str, **kwargs: Any) -> None:
        self.records.append(("info", message, dict(kwargs)))

    def warning(self, message: str, **kwargs: Any) -> None:
        self.records.append(("warning", message, dict(kwargs)))

    def error(self, message: str, **kwargs: Any) -> None:
        self.records.append(("error", message, dict(kwargs)))


def test_fastapi_canonical_request_emits_single_event_with_route_context() -> None:
    logger = CapturingLogger()
    app = FastAPI()
    app.add_middleware(RequestLoggerMiddleware, logger=logger, canonical=True)

    @app.get("/users/{user_id}")
    async def get_user(user_id: str) -> dict[str, str]:
        assert get_request_id() == "req-real"
        assert add_event_fields({"user.id": user_id}, feature_checkout_v2=True)
        return {"request_id": get_request_id()}

    client = FastAPITestClient(app)
    response = client.get(
        "/users/42?page=1&access_token=secret",
        headers={
            "x-request-id": "req-real",
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "user-agent": "integration-test",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"request_id": "req-real"}
    assert get_request_id() == ""
    assert len(logger.records) == 1

    level, message, event = logger.records[0]
    assert level == "info"
    assert message == "http.request"
    assert event["event"] == "http.request"
    assert event["request_id"] == "req-real"
    assert event["method"] == "GET"
    assert event["path"] == "/users/42"
    assert event["route"] == "/users/{user_id}"
    assert event["status_code"] == 200
    assert event["outcome"] == "success"
    assert event["user_agent"] == "integration-test"
    assert event["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert event["span_id"] == "00f067aa0ba902b7"
    assert event["query"] == {"page": "1", "access_token": "***"}
    assert event["user.id"] == "42"
    assert event["feature_checkout_v2"] is True
    assert isinstance(event["duration_ms"], float)
    assert logger.contexts == [{"request_id": "req-real", "path": "/users/42"}]


def test_fastapi_canonical_request_generates_short_id_without_header() -> None:
    logger = CapturingLogger()
    app = FastAPI()
    app.add_middleware(RequestLoggerMiddleware, logger=logger, canonical=True)

    @app.get("/request-id")
    async def read_request_id() -> dict[str, str]:
        return {"request_id": get_request_id()}

    client = FastAPITestClient(app)
    response = client.get("/request-id")

    assert response.status_code == 200
    generated_request_id = response.json()["request_id"]
    assert len(generated_request_id) == 8
    assert all(c in "0123456789abcdef" for c in generated_request_id)
    assert logger.records[0][2]["request_id"] == generated_request_id


def test_starlette_canonical_sampling_drops_success_but_keeps_exception() -> None:
    logger = CapturingLogger()

    async def ok(_request: Any) -> JSONResponse:
        add_event_fields(endpoint="ok")
        return JSONResponse({"ok": True})

    async def boom(_request: Any) -> JSONResponse:
        add_event_fields(endpoint="boom")
        raise RuntimeError("database down")

    app = Starlette(
        routes=[
            Route("/ok", ok),
            Route("/boom", boom),
        ]
    )
    app.add_middleware(
        RequestLoggerMiddleware,
        logger=logger,
        canonical=True,
        sample_rate=0.0,
    )

    client = StarletteTestClient(app, raise_server_exceptions=False)

    ok_response = client.get("/ok")
    assert ok_response.status_code == 200
    assert logger.records == []

    boom_response = client.get("/boom")
    assert boom_response.status_code == 500
    assert len(logger.records) == 1

    level, message, event = logger.records[0]
    assert level == "error"
    assert message == "http.request"
    assert event["path"] == "/boom"
    assert event["route"] == "/boom"
    assert event["status_code"] == 500
    assert event["outcome"] == "error"
    assert event["error.type"] == "RuntimeError"
    assert event["error.message"] == "database down"
    assert event["endpoint"] == "boom"
