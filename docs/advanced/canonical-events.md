# Canonical Events { #canonical-events }

A typical web request produces a handful of log lines: "request started", "user loaded", "payment sent", "request completed"... To understand what happened in **one** request, you have to find all of its lines and put them back together.

A **canonical event** (also called a **wide event**) turns that around: you emit **one** structured event per request, when it finishes, with everything you know about it. The method, the route, the status, the duration, and also the user, the feature flags, the payment provider... all in one place.

One wide event is much easier to search, aggregate, sample, and alert on. 🎉

Logust's FastAPI / Starlette middleware can emit these events for you. This page explains how they work. To set up the middleware in your app, see [FastAPI](../how-to/fastapi.md).

/// info

The middleware needs the web extra that matches your framework:

<div class="termy">

```console
$ pip install "logust[fastapi]"

---> 100%
```

</div>

Or `pip install "logust[starlette]"` for Starlette.

///

## One event per request { #one-event-per-request }

Add `RequestLoggerMiddleware` with `canonical=True`, and use `add_event_fields()` in your endpoints to add your own fields to the event:

```python hl_lines="14 19"
--8<-- "docs_src/advanced_canonical_events/tutorial001.py"
```

The example uses FastAPI's `TestClient` to send a request without starting a server. Run it, and you get one JSON line:

<div class="termy">

```console
$ python main.py

{"time":"2026-10-06 12:10:57.604","level":"INFO","message":"http.request","name":"logust.contrib.starlette","function":"_emit_canonical_event","line":429,"extra":{"event":"http.request","path":"/checkout","route":"/checkout","payment_provider":"stripe","items":3,"status_code":200,"outcome":"success","query":{"user_id":"u_123"},"duration_ms":0.68,"user.id":"u_123","client_ip":"testclient","user_agent":"testclient","request_id":"1c581bfe","method":"POST"}}
```

</div>

Here's the same event, pretty-printed:

```json hl_lines="12 13 20"
{
  "time": "2026-10-06 12:10:57.604",
  "level": "INFO",
  "message": "http.request",
  "name": "logust.contrib.starlette",
  "function": "_emit_canonical_event",
  "line": 429,
  "extra": {
    "event": "http.request",
    "path": "/checkout",
    "route": "/checkout",
    "payment_provider": "stripe",
    "items": 3,
    "status_code": 200,
    "outcome": "success",
    "query": {
      "user_id": "u_123"
    },
    "duration_ms": 0.68,
    "user.id": "u_123",
    "client_ip": "testclient",
    "user_agent": "testclient",
    "request_id": "1c581bfe",
    "method": "POST"
  }
}
```

The middleware filled in the request and response data, and your endpoint added `user.id`, `payment_provider` and `items` to the **same** event.

The event is emitted **after** the response is complete, so the status and the duration are known. Its level depends on the result: `INFO` for success, `WARNING` for 4xx responses, `ERROR` for 5xx responses and exceptions.

/// tip

With `setup_fastapi(app, canonical=True, ...)` you get the same middleware in one line, and standard `logging` is redirected to Logust too. See [FastAPI](../how-to/fastapi.md).

///

## The event fields { #the-event-fields }

The fields go in `extra`, so they work with every sink. With `serialize=True`, numbers, booleans, lists, dicts and `null` stay native JSON types.

| Field | Value |
|-------|-------|
| `event` | Always `"http.request"`. |
| `request_id` | The incoming `x-request-id` header if there's one, otherwise an 8-character `uuid4` prefix. See [Request IDs](#request-ids). |
| `method`, `path` | The HTTP method and the actual path, like `/users/42`. |
| `route` | The route **template**, like `/users/{user_id}`. Great for grouping. |
| `client_ip` | From `x-forwarded-for`, then `x-real-ip`, then the connection. |
| `user_agent` | The `user-agent` header, when present. |
| `trace_id`, `span_id` | From a W3C `traceparent` header, when present. |
| `query` | The query parameters, when there are some, with sensitive values masked. |
| `request_body` | With `include_request_body=True`, the body, with sensitive fields masked and truncated to `max_body_size`. |
| `status_code` | The response status. |
| `duration_ms` | The request duration in milliseconds. |
| `outcome` | `"success"`, `"client_error"` (4xx) or `"error"` (5xx and exceptions). |
| `error.type`, `error.message` | The exception class and message, when the endpoint raised. |

Sensitive names (`password`, `token`, `secret`, `api_key`, `authorization`...) are masked as `"***"` in `query` and `request_body`.

## Adding fields { #adding-fields }

`add_event_fields()` adds fields to the event of the **current request**, from anywhere: the endpoint, a dependency, a service function deep in your code. You don't need to pass anything around.

It accepts a dict, keyword arguments, or both:

```python
add_event_fields(
    {"user.id": user_id, "payment.amount": amount},  # Dotted names need a dict
    feature_payments_v2=True,
)
```

It returns `True` when an event is active, and `False` outside of one (in a script, a test, a background task...). So shared code can call it without checking first.

There are a few more helpers in `logust.contrib`:

* `get_event_fields()` returns a **copy** of the current fields (an empty dict outside an event).
* `get_current_event()` returns the event dict itself, or `None`.
* `clear_event_fields()` removes all the fields of the current event.

/// tip

Add the fields that will help you **answer questions later**: the user and tenant, the feature flags that were on, the plan, the cache hit or miss, the number of items. A wide event with 20 useful fields beats 20 log lines. 😎

///

## Tail sampling { #tail-sampling }

A busy service handles a lot of boring, successful, fast requests. Storing all of them can get expensive. But you want to keep **all** the errors and slow requests.

That's what **tail sampling** does: it decides whether to keep an event **after** the request finished, when the status and the duration are known.

```python hl_lines="21-23"
--8<-- "docs_src/advanced_canonical_events/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

INFO    | /slow 200 success 60.965ms
ERROR   | /broken 500 error 0.228ms
```

</div>

Four requests were made, but only two events were kept:

* The two `/fast` requests are normal, and `sample_rate=0.0` keeps none of them.
* `/slow` took more than `slow_ms=50` milliseconds, so it's kept.
* `/broken` raised an exception, and `always_keep_errors=True` keeps it.

The rules, in order:

1. With `always_keep_errors=True` (the default), keep 5xx responses and exceptions.
2. If `slow_ms` is set, keep requests that took at least that many milliseconds.
3. Keep a `sample_rate` fraction (`0.0` to `1.0`, default `1.0`) of the rest, at random.

In production, you'd use something like `sample_rate=0.05` to keep 5% of the normal traffic. `sample_rate` must be between `0.0` and `1.0`, and `slow_ms` greater than or equal to `0`.

/// note

Sampling only applies to the canonical event. Messages you log yourself during the request are always written.

///

## Custom samplers { #custom-samplers }

For your own rules, pass a `sampler`. A `TailSampler` takes the same options (`rate`, `slow_ms`, `always_keep_errors`), plus `keep_if`, a function that receives the event and returns `True` to always keep it:

```python hl_lines="17-21"
--8<-- "docs_src/advanced_canonical_events/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

INFO    | /reports tenant=enterprise
```

</div>

Your enterprise customers' requests are always kept, the others are sampled (here at `0.0`, to make the example predictable).

`keep_if` runs **first**, so it can keep an event that the other rules would drop. Since the event includes the fields you added with `add_event_fields()`, you can keep events based on your own data.

You can also pass a plain function:

```python
app.add_middleware(
    RequestLoggerMiddleware,
    canonical=True,
    sampler=lambda event: event.get("route") == "/checkout",
)
```

When you pass `sampler`, it **replaces** `sample_rate`, `slow_ms` and `always_keep_errors`. A function sampler decides alone, so remember to keep the errors yourself if you want them.

## Request IDs { #request-ids }

Each request gets an ID. If the client (or your load balancer) sends an `x-request-id` header, the middleware uses it. Otherwise, it generates a short one.

The ID is in the canonical event, in every message you log during the request (as `extra["request_id"]`), and `get_request_id()` gives it to your code:

```python hl_lines="18-19 23-24"
--8<-- "docs_src/advanced_canonical_events/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

INFO    | req-abc-123 | Loading the profile
INFO    | req-abc-123 | http.request
{'request_id': 'req-abc-123'}
INFO    | 8bcd1a02 | Loading the profile
INFO    | 8bcd1a02 | http.request
{'request_id': '8bcd1a02'}
```

</div>

The first request sent `x-request-id: req-abc-123`, and the ID was kept. The second had none, so the middleware generated `8bcd1a02`.

Return the ID to the client (in a response header or an error body), and support can find the exact event for a bug report. ✨

`get_request_id()` returns an empty string outside a request. An incoming ID is sanitized: characters outside printable ASCII are dropped, and it's truncated to 128 characters.

/// warning

The `request_id` in the extra of your own messages comes from [`contextualize()`](../tutorial/context.md), which is currently shared by concurrent requests (see [Threads and Processes](threads-and-processes.md#threads)). The value in the canonical event itself, and `get_request_id()`, are always those of the current request.

///

## Canonical events without a web framework { #canonical-events-without-a-web-framework }

The idea works for anything that has a clear start and end: a background job, a CLI command, a queue message. Use `canonical_event()` to open an event, add fields from anywhere inside, and log it at the end:

```python hl_lines="13 18-19 22"
--8<-- "docs_src/advanced_canonical_events/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

{"time":"2026-10-06 12:12:48.584","level":"INFO","message":"job.invoices","name":"__main__","function":"run_job","line":22,"extra":{"batch":"2026-10","invoices_sent":3,"event":"job.invoices","duration_ms":0.015}}
Outside an event: False
```

</div>

`canonical_event()` is a context manager. It yields the event dict, with the fields you passed it, and while the `with` block runs, `add_event_fields()` (here, in `send_invoices()`) adds to it. Nested events restore the outer one when they end.

The event is stored in a context variable, so each thread and each asyncio task has its own.

## Recap { #recap }

* A canonical event is **one** wide, structured event per request, emitted when it's done.
* `RequestLoggerMiddleware(canonical=True)` or `setup_fastapi(app, canonical=True)` emits them as `http.request`.
* `add_event_fields()` adds your own fields from anywhere in the request.
* Tail sampling keeps errors and slow requests, and a `sample_rate` of the rest.
* `TailSampler(keep_if=...)` or a plain function gives you custom rules.
* `get_request_id()` gives the request ID, which honors `x-request-id`.
* `canonical_event()` brings the same idea to jobs and scripts.
