# Canonical Events

Canonical request events are single, structured events emitted after a request
finishes. They are designed for production web services where one wide event is
easier to search, sample, and alert on than separate "request started" and
"request completed" lines.

## Install

Use the web extra that matches your framework:

```bash
pip install "logust[fastapi]"
# or
pip install "logust[starlette]"
```

## FastAPI Setup

```python
from fastapi import FastAPI
from logust import logger
from logust.contrib import add_event_fields
from logust.contrib.starlette import setup_fastapi

app = FastAPI()
logger.add("logs/app.json", serialize=True)

setup_fastapi(
    app,
    canonical=True,
    sample_rate=0.05,
    slow_ms=1000,
    skip_routes=["/health"],
)

@app.post("/checkout")
async def checkout(user_id: str):
    add_event_fields(
        {"user.id": user_id},
        feature_checkout_v2=True,
        payment_provider="stripe",
    )
    return {"ok": True}
```

With `canonical=True`, Logust emits one `http.request` event at the end of the
request. Endpoint code can call `add_event_fields()` to enrich that same final
event.

## Event Shape

A successful request produces fields like these:

```json
{
  "message": "http.request",
  "extra": {
    "event": "http.request",
    "request_id": "a1b2c3d4",
    "method": "POST",
    "path": "/checkout",
    "route": "/checkout",
    "client_ip": "127.0.0.1",
    "user_agent": "curl/8.0.0",
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7",
    "status_code": 200,
    "duration_ms": 34.2,
    "outcome": "success",
    "user.id": "u_123",
    "feature_checkout_v2": true
  }
}
```

Important fields:

- `request_id`: incoming `x-request-id` when present; otherwise an 8-character `uuid4` prefix.
- `route`: framework route template, such as `/users/{user_id}`.
- `outcome`: `success`, `client_error`, or `error`.
- `duration_ms`: request duration in milliseconds.
- `query` and `request_body`: included when configured, with sensitive fields masked.
- `error.type` and `error.message`: included for exception paths.

JSON sinks preserve numeric, boolean, list, dict, and null extra values as native
JSON types.

## Tail Sampling

Tail sampling decides whether to keep the completed event after status code and
duration are known.

```python
setup_fastapi(
    app,
    canonical=True,
    sample_rate=0.01,
    slow_ms=750,
    always_keep_errors=True,
)
```

The default policy keeps:

- 5xx responses and exceptions when `always_keep_errors=True`
- requests at or above `slow_ms`
- a `sample_rate` fraction of normal successful requests

`sample_rate` must be between `0.0` and `1.0`. `slow_ms` must be greater than or
equal to `0`.

## Custom Samplers

Use `TailSampler` when you need predictable rules:

```python
from logust.contrib import TailSampler

setup_fastapi(
    app,
    canonical=True,
    sampler=TailSampler(
        rate=0.01,
        slow_ms=750,
        keep_if=lambda event: event.get("tenant") == "enterprise",
    ),
)
```

You can also pass a predicate directly:

```python
setup_fastapi(
    app,
    canonical=True,
    sampler=lambda event: event.get("path") == "/important",
)
```

When `sampler` is provided, it replaces `sample_rate`, `slow_ms`, and
`always_keep_errors`.

## Adding Fields

Use `add_event_fields()` from anywhere inside the request:

```python
from logust.contrib import add_event_fields

@app.post("/payments")
async def create_payment(user_id: str, amount: float):
    add_event_fields(
        {
            "user.id": user_id,
            "payment.amount": amount,
            "payment.currency": "USD",
        },
        feature_payments_v2=True,
    )
    return {"ok": True}
```

`add_event_fields()` returns `True` when a canonical event is active. Outside a
canonical request event it returns `False`, so shared helper code can call it
without special casing.

## Request IDs

Use `get_request_id()` to access the active request ID:

```python
from logust.contrib.starlette import get_request_id

@app.get("/me")
async def me():
    return {"request_id": get_request_id()}
```

The request ID is reset when the request finishes.

## Full Example

See the runnable FastAPI example:

```bash
python examples/08_fastapi_integration.py
```

It writes JSON logs to `logs/app.json` and demonstrates route templates,
request-scoped fields, request ID propagation, tail sampling, and error events.
