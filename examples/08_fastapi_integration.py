#!/usr/bin/env python3
"""FastAPI canonical request logging with Logust.

This example uses Logust's built-in FastAPI/Starlette middleware to emit one
structured ``http.request`` event after each request completes.

Requirements:
    pip install "logust[fastapi]" uvicorn

Run:
    python examples/08_fastapi_integration.py

Try:
    curl -H "x-request-id: req-demo" "http://localhost:8000/users/123?plan=pro"
    curl -X POST "http://localhost:8000/checkout?user_id=u_123"
    curl "http://localhost:8000/error"

Logs:
    logs/app.json
"""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from time import sleep
from typing import Any

from logust import logger
from logust.contrib import TailSampler, add_event_fields, log_fn

try:
    from fastapi import FastAPI, HTTPException

    from logust.contrib.starlette import get_request_id, setup_fastapi
except ImportError:
    print("FastAPI support is not installed. Install it with:")
    print('  pip install "logust[fastapi]" uvicorn')
    sys.exit(1)


LOG_DIR = Path("logs")
JSON_LOG = LOG_DIR / "app.json"


def configure_logging() -> None:
    """Configure Logust sinks for the demo app."""
    LOG_DIR.mkdir(exist_ok=True)

    logger.set_level("INFO")
    logger.add(
        JSON_LOG,
        serialize=True,
        rotation="100 MB",
        retention="7 days",
        enqueue=True,
    )
    logger.info("FastAPI logging configured", log_file=str(JSON_LOG))


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    logger.info("Application startup")
    yield
    logger.info("Application shutdown")
    logger.complete()


app = FastAPI(title="Logust FastAPI Canonical Events", lifespan=lifespan)

setup_fastapi(
    app,
    canonical=True,
    skip_routes=["/health"],
    sampler=TailSampler(
        rate=0.25,
        slow_ms=750,
        keep_if=lambda event: event.get("tenant") == "enterprise",
    ),
)


@log_fn
def load_user_from_db(user_id: int) -> dict[str, Any]:
    """Pretend to load a user from storage."""
    if user_id == 500:
        sleep(0.8)
    return {
        "id": user_id,
        "name": f"User {user_id}",
        "plan": "enterprise" if user_id == 42 else "free",
    }


@app.get("/")
async def root() -> dict[str, str]:
    add_event_fields(endpoint="root")
    return {
        "message": "Logust FastAPI example",
        "request_id": get_request_id(),
    }


@app.get("/users/{user_id}")
async def get_user(user_id: int, plan: str | None = None) -> dict[str, Any]:
    user = load_user_from_db(user_id)
    tenant = plan or user["plan"]

    add_event_fields(
        {
            "user.id": str(user_id),
            "tenant": tenant,
            "feature.canonical_events": True,
        }
    )

    if user_id <= 0:
        add_event_fields(validation_error="invalid_user_id")
        raise HTTPException(status_code=400, detail="user_id must be positive")

    return {
        "request_id": get_request_id(),
        "user": user,
    }


@app.post("/checkout")
async def checkout(user_id: str, amount: float = 49.99) -> dict[str, Any]:
    add_event_fields(
        {
            "event.domain": "checkout",
            "user.id": user_id,
            "payment.amount": amount,
            "payment.currency": "USD",
        },
        feature_checkout_v2=True,
    )
    logger.info("Checkout accepted", user_id=user_id, amount=amount)
    return {"ok": True, "request_id": get_request_id()}


@app.get("/error")
async def trigger_error() -> None:
    add_event_fields(endpoint="error_demo")
    raise RuntimeError("intentional demo error")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is not installed. Install it with:")
        print("  pip install uvicorn")
        sys.exit(1)

    print("Starting Logust FastAPI example on http://localhost:8000")
    print(f"JSON logs will be written to {JSON_LOG}")
    print("Press Ctrl+C to stop")
    uvicorn.run(app, host="127.0.0.1", port=8000)
