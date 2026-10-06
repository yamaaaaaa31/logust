# FastAPI and Starlette { #fastapi-and-starlette }

When you run a web API, you usually want a log line for **every request**: what was called, how long it took, what status it returned, and a **request ID** to connect all the logs of one request.

Logust comes with a middleware for <a href="https://fastapi.tiangolo.com" class="external-link" target="_blank">FastAPI</a> and <a href="https://www.starlette.io" class="external-link" target="_blank">Starlette</a> that does all of that for you. 😎

## Install { #install }

Install Logust with the extra for your framework:

//// tab | FastAPI

<div class="termy">

```console
$ pip install "logust[fastapi]"

---> 100%
```

</div>

////

//// tab | Starlette

<div class="termy">

```console
$ pip install "logust[starlette]"

---> 100%
```

</div>

////

## Add the middleware { #add-the-middleware }

Add `RequestLoggerMiddleware` to your app:

```python hl_lines="3 6"
--8<-- "docs_src/how_to_fastapi/tutorial001.py"
```

Run it with your ASGI server, for example Uvicorn, and send a couple of requests to `/users/42` and `/nope`:

<div class="termy">

```console
$ uvicorn main:app

INFO:     Started server process [30353]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
2026-10-06 11:58:43.174 | INFO     | logust.contrib.starlette:_log_request_start:488 - Request started: GET /users/42 ip=127.0.0.1
2026-10-06 11:58:43.175 | INFO     | logust.contrib.starlette:_log_response:509 - Request successful: GET /users/42 status=200 time=0.0007s ip=127.0.0.1
INFO:     127.0.0.1:59248 - "GET /users/42 HTTP/1.1" 200 OK
2026-10-06 11:58:43.380 | INFO     | logust.contrib.starlette:_log_request_start:488 - Request started: GET /nope ip=127.0.0.1
2026-10-06 11:58:43.380 | WARNING  | logust.contrib.starlette:_log_response:507 - Request failed: GET /nope status=404 time=0.0003s ip=127.0.0.1
INFO:     127.0.0.1:59250 - "GET /nope HTTP/1.1" 404 Not Found
```

</div>

Each request gives you two lines: one when it starts, and one with the status and the time it took. The level follows the status code:

* `INFO` for `1xx`, `2xx` and `3xx`.
* `WARNING` for `4xx`.
* `ERROR` for `5xx`, and for unhandled exceptions (`Request failed: GET /path error=ValueError time=... ip=...`).

The client IP is read from the `X-Forwarded-For` header first, then `X-Real-IP`, then the connection itself.

/// info

The `INFO:     127.0.0.1:59248 - ...` lines are Uvicorn's own access log, written with the standard `logging` module. The one-liner [below](#one-liner-setup) sends those through Logust too.

///

## Configuration options { #configuration-options }

You can configure what is logged with keyword arguments to `add_middleware()`:

```python hl_lines="8-12"
--8<-- "docs_src/how_to_fastapi/tutorial002.py"
```

* `skip_routes`: paths that are not logged. A path is skipped when it **starts with** one of them, so `"/health"` also skips `/healthz` and `/health/db`.
* `skip_regexes`: regular expressions; a path is skipped when one of them matches its beginning (`re.match()`).
* `include_request_body`: log the body of `POST`, `PUT`, `PATCH` and `DELETE` requests. Multipart bodies are not read; they are logged as `<multipart: size=...>`. Default: `False`.
* `max_body_size`: logged bodies longer than this are cut and end with `...`. It must be `0` or more. Default: `1000`.
* `mask_sensitive_data`: hide sensitive values in logged bodies and query parameters. Default: `True`. See [Sensitive data masking](#sensitive-data-masking).
* `logger`: the Logust logger to use. Default: the global `logger`.

The middleware also takes the options for canonical events (`canonical`, `sample_rate`, `slow_ms`, `always_keep_errors` and `sampler`), covered in [Canonical request events](#canonical-request-events).

With this app, requests to `/health` and `/docs` are not logged, and a login request logs its body with the password hidden:

<div class="termy">

```console
$ uvicorn main:app

INFO:     127.0.0.1:59373 - "GET /health HTTP/1.1" 200 OK
2026-10-06 11:59:02.422 | INFO     | logust.contrib.starlette:_log_request_start:488 - Request started: POST /login ip=127.0.0.1 body={"username": "john", "password": "***"}
2026-10-06 11:59:02.423 | INFO     | logust.contrib.starlette:_log_response:509 - Request successful: POST /login status=200 time=0.0016s ip=127.0.0.1
INFO:     127.0.0.1:59374 - "POST /login HTTP/1.1" 200 OK
```

</div>

## One-liner setup { #one-liner-setup }

For the quickest setup, use `setup_fastapi()`:

```python hl_lines="3 6"
--8<-- "docs_src/how_to_fastapi/tutorial003.py"
```

It does two things:

* It adds `RequestLoggerMiddleware`, passing it `skip_routes`, `skip_regexes`, `include_request_body` and the canonical event options.
* It calls [`intercept_logging()`](intercept-standard-logging.md), so the standard `logging` records of Uvicorn, FastAPI and your other libraries go through Logust too. Pass `intercept_logging=False` to skip this.

Now everything uses the Logust format, including Uvicorn's startup and access logs:

<div class="termy">

```console
$ uvicorn main:app

2026-10-06 11:58:48.462 | DEBUG    | ::0 - Using selector: KqueueSelector
2026-10-06 11:58:48.467 | INFO     | ::0 - Started server process [30849]
2026-10-06 11:58:48.467 | INFO     | ::0 - Waiting for application startup.
2026-10-06 11:58:48.467 | INFO     | ::0 - Application startup complete.
2026-10-06 11:58:49.822 | INFO     | ::0 - 127.0.0.1:59283 - "GET /health HTTP/1.1" 200
2026-10-06 11:58:50.028 | INFO     | logust.contrib.starlette:_log_request_start:488 - Request started: GET /items/7 ip=127.0.0.1 query={'q': 'shoes', 'token': '***'}
2026-10-06 11:58:50.028 | INFO     | logust.contrib.starlette:_log_response:509 - Request successful: GET /items/7 status=200 time=0.0004s ip=127.0.0.1
2026-10-06 11:58:50.028 | INFO     | ::0 - 127.0.0.1:59284 - "GET /items/7?q=shoes&token=xyz HTTP/1.1" 200
```

</div>

The `::0` on the Uvicorn lines is because records from the standard `logging` module have no caller fields. See [A format for intercepted records](intercept-standard-logging.md#a-format-for-intercepted-records) for a format that looks cleaner.

/// warning

`skip_routes` and masking only apply to the Logust middleware. Uvicorn's **access log** is separate: above, it still logs `/health`, and it logs the query string with `token=xyz` in clear text.

If that matters for you, run Uvicorn with `--no-access-log`; the middleware already logs every request.

///

## Request ID access { #request-id-access }

The middleware gives every request an **ID**. If the request has an `X-Request-ID` header, its value is used (non-printable characters and spaces are removed, and it is cut to 128 characters). Otherwise, a new short ID is generated, like `1b67cc35`.

While the request is handled, the ID is:

* Available anywhere in your code, with `get_request_id()`.
* Bound to every Logust message as the extra fields `request_id` and `path`, using [`contextualize()`](../tutorial/context.md#temporary-context-with-contextualize). The values are [context-local](../tutorial/context.md#context-local): when many requests are handled at the same time, each message gets the ID of its own request.

The default format doesn't show extra fields, so let's add `{extra[request_id]}` to it:

```python hl_lines="6 11 20-21"
--8<-- "docs_src/how_to_fastapi/tutorial004.py"
```

Now all the logs of a request share its ID, including the ones from your own code. The second request sent `X-Request-ID: req-123`:

<div class="termy">

```console
$ uvicorn main:app

2026-10-06 11:59:08.212 | INFO     | 1b67cc35 | Request started: GET /users/42 ip=127.0.0.1
2026-10-06 11:59:08.212 | INFO     | 1b67cc35 | Loading user 42
2026-10-06 11:59:08.213 | INFO     | 1b67cc35 | Request successful: GET /users/42 status=200 time=0.0005s ip=127.0.0.1
2026-10-06 11:59:08.213 | INFO     |  | 127.0.0.1:59415 - "GET /users/42 HTTP/1.1" 200
2026-10-06 11:59:08.419 | INFO     | req-123 | Request started: GET /users/7 ip=127.0.0.1
2026-10-06 11:59:08.419 | INFO     | req-123 | Loading user 7
2026-10-06 11:59:08.419 | INFO     | req-123 | Request successful: GET /users/7 status=200 time=0.0006s ip=127.0.0.1
2026-10-06 11:59:08.419 | INFO     |  | 127.0.0.1:59418 - "GET /users/7 HTTP/1.1" 200
```

</div>

The Uvicorn access lines are written after the middleware is done, so they have no request ID, and `{extra[request_id]}` is empty there.

`get_request_id()` returns `""` outside of a request.

/// tip

With [JSON output](../tutorial/json-output.md) (`serialize=True`), you don't need to change any format: `request_id` and `path` are in the `extra` object of every record.

///

## Sensitive data masking { #sensitive-data-masking }

With `mask_sensitive_data=True` (the default), the middleware replaces sensitive values with `"***"` in:

* Logged **request bodies** that are JSON, at any depth (nested objects and lists too).
* Logged **query parameters**.

A key is sensitive when its name, ignoring case, **contains** one of:

* `password`, `passwd`
* `token`, `access_token`, `refresh_token`, `jwt`
* `secret`, `key`, `api_key`
* `authorization`, `credential`

So `password`, `api_key`, `X-Api-Key` and `monkey` are all masked:

```text
Request body: {"username": "john", "password": "secret123", "api_key": "abc"}
Logged as:    {"username": "john", "password": "***", "api_key": "***"}
```

Bodies that are not JSON are logged as they are, without masking (cut to `max_body_size`).

/// note

Masking happens **before** the body is cut to `max_body_size`, so a long body never shows a partly masked value.

///

## Canonical request events { #canonical-request-events }

Two text lines per request are great to read in a terminal. In production, with a log aggregator, it's often better to have **one structured event per request**, with every field you might want to query: the route, the status, the duration, the user, feature flags...

That's what **canonical mode** does. You can read all about the idea in [Canonical Events](../advanced/canonical-events.md); here is how to set it up.

### Turn it on { #turn-it-on }

Pass `canonical=True`, and add your own fields from anywhere in the request with `add_event_fields()`:

```python hl_lines="4 7 10 15-19"
--8<-- "docs_src/how_to_fastapi/tutorial005.py"
```

Instead of the start and response lines, the middleware now logs one `http.request` message after the response is complete. Its fields are in `extra`, so you see them with `serialize=True`. Here is the line written to `app.json` for `POST /checkout?user_id=u_123`, formatted for reading:

```json
{
  "time": "2026-10-06 11:59:45.131",
  "level": "INFO",
  "message": "http.request",
  "name": "logust.contrib.starlette",
  "function": "_emit_canonical_event",
  "line": 429,
  "extra": {
    "method": "POST",
    "query": {"user_id": "u_123"},
    "request_id": "req-123",
    "status_code": 200,
    "path": "/checkout",
    "client_ip": "127.0.0.1",
    "route": "/checkout",
    "feature_checkout_v2": true,
    "event": "http.request",
    "user.id": "u_123",
    "duration_ms": 2.495,
    "outcome": "success",
    "user_agent": "curl/8.7.1",
    "payment_provider": "stripe"
  }
}
```

The event has:

* `event`, `request_id`, `method`, `path`, `route` (the route template, like `/users/{user_id}`), `client_ip`.
* `status_code`, `duration_ms`, and `outcome`: `"success"`, `"client_error"` (`4xx`) or `"error"` (`5xx` or an exception).
* `user_agent`, `query` (masked) and `request_body` (masked, with `include_request_body=True`), when present.
* `trace_id` and `span_id`, when the request has a valid W3C `traceparent` header.
* `error.type` and `error.message`, when the app raised an exception.
* Every field you added with `add_event_fields()`.

The level is `INFO`, `WARNING` for `4xx`, and `ERROR` for `5xx` and exceptions.

`add_event_fields()` accepts a dict, keyword arguments, or both. A dict is handy for keys that are not valid Python names, like `"user.id"`. It returns `True` when a canonical event is active, and `False` (doing nothing) outside of one.

### Keep only the events that matter { #keep-only-the-events-that-matter }

With a lot of traffic, you probably don't need an event for every successful request. **Tail sampling** decides, after the request is done, whether to keep its event:

```python hl_lines="13-14"
--8<-- "docs_src/how_to_fastapi/tutorial006.py"
```

* `sample_rate`: the fraction of normal events to keep, from `0.0` to `1.0`. Default: `1.0` (keep all).
* `slow_ms`: always keep events with `duration_ms` at or above this. Must be `0` or more. Default: `None`.
* `always_keep_errors`: always keep `5xx` and exception events. Default: `True`.

Here, you keep about 2% of the normal requests, but **every** slow one and **every** error. 🎉

### Custom rules with `TailSampler` { #custom-rules-with-tailsampler }

For your own rules, pass a `TailSampler`, or any function that takes the event and returns `True` to keep it, as `sampler`:

```python hl_lines="3 10-14"
--8<-- "docs_src/how_to_fastapi/tutorial007.py"
```

`TailSampler(rate=1.0, always_keep_errors=True, slow_ms=None, keep_if=None)` keeps an event when `keep_if(event)` is true, or it is an error (with `always_keep_errors`), or it is slow, and otherwise keeps a `rate` fraction of them.

/// warning

When you pass `sampler`, it **replaces** `sample_rate`, `slow_ms` and `always_keep_errors`: those arguments are ignored.

///

You can find the full event contract and more examples in [Canonical Events](../advanced/canonical-events.md).

## Flush file logs on shutdown { #flush-file-logs-on-shutdown }

File sinks are buffered, and the buffer is written when the program exits normally. But Uvicorn, when it receives `SIGTERM` (the signal Docker and Kubernetes send to stop a container), ends the process in a way that skips that, and the last messages written to files can be **lost**.

Call [`logger.complete()`](../tutorial/file-output.md#make-sure-its-written) when the app shuts down, in the `lifespan`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    logger.complete()


app = FastAPI(lifespan=lifespan)
```

You will see it in the complete example below.

## Complete example { #complete-example }

Here's a FastAPI application with all the pieces together: the one-liner setup, files with rotation and JSON, a [timing decorator](timing-decorators.md), and a clean shutdown:

```python
--8<-- "docs_src/how_to_fastapi/tutorial008.py"
```

<div class="termy">

```console
$ uvicorn main:app

2026-10-06 11:59:52.442 | INFO     | ::0 - Started server process [36464]
2026-10-06 11:59:52.442 | INFO     | ::0 - Waiting for application startup.
2026-10-06 11:59:52.442 | INFO     | ::0 - Application startup complete.
2026-10-06 11:59:53.742 | INFO     | logust.contrib.starlette:_log_request_start:488 - Request started: GET /users/1 ip=127.0.0.1
2026-10-06 11:59:53.743 | INFO     | main:read_user:29 - Called get_user_from_db with elapsed_time=0.000
2026-10-06 11:59:53.744 | INFO     | logust.contrib.starlette:_log_response:509 - Request successful: GET /users/1 status=200 time=0.0015s ip=127.0.0.1
2026-10-06 11:59:53.744 | INFO     | ::0 - 127.0.0.1:59930 - "GET /users/1 HTTP/1.1" 200
2026-10-06 11:59:53.949 | INFO     | ::0 - 127.0.0.1:59931 - "GET /health HTTP/1.1" 200
```

</div>

`/health` is not logged by the middleware (only by Uvicorn's access log). In `app.json`, the three request lines carry the same `request_id`:

```json
{"time":"2026-10-06 11:59:53.742","level":"INFO","message":"Request started: GET /users/1 ip=127.0.0.1","name":"logust.contrib.starlette","function":"_log_request_start","line":488,"extra":{"request_id":"22ce10d8","path":"/users/1"}}
{"time":"2026-10-06 11:59:53.743","level":"INFO","message":"Called get_user_from_db with elapsed_time=0.000","name":"main","function":"read_user","line":29,"extra":{"request_id":"22ce10d8","path":"/users/1"}}
{"time":"2026-10-06 11:59:53.744","level":"INFO","message":"Request successful: GET /users/1 status=200 time=0.0015s ip=127.0.0.1","name":"logust.contrib.starlette","function":"_log_response","line":509,"extra":{"request_id":"22ce10d8","path":"/users/1"}}
```

## Recap { #recap }

* `app.add_middleware(RequestLoggerMiddleware)` logs every request with its status and timing.
* `setup_fastapi(app)` adds the middleware **and** routes standard `logging` (Uvicorn included) through Logust.
* Skip paths with `skip_routes` (prefixes) and `skip_regexes`; log bodies with `include_request_body=True`.
* Every request gets an ID: `get_request_id()` in your code, `extra["request_id"]` in every record.
* Sensitive keys in bodies and query parameters are masked as `"***"` by default.
* `canonical=True` logs one structured `http.request` event per request; add fields with `add_event_fields()` and sample with `sample_rate`, `slow_ms` or a `TailSampler`.
* Call `logger.complete()` on shutdown so file logs are not lost.
