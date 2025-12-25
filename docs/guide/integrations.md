# Integrations

Logust provides zero-config integrations for common use cases in the `logust.contrib` module.

## Standard Logging Interception

Redirect all standard library logging to logust with a single line:

```python
from logust.contrib import intercept_logging

# That's it! All logging now goes through logust
intercept_logging()

# Standard logging calls now use logust
import logging
logging.info("This goes through logust!")

# Third-party libraries automatically use logust too
import requests  # Their logs appear in logust format
```

### How It Works

The `InterceptHandler` captures log records from Python's standard `logging` module and forwards them to logust. This means:

- Consistent log formatting across your entire application
- Third-party library logs use logust's fast Rust core
- All logs benefit from logust's rotation, retention, and JSON features

### Manual Setup

For more control, you can set up the handler manually:

```python
import logging
from logust.contrib import InterceptHandler

# Clear existing handlers
logging.root.handlers = [InterceptHandler()]
logging.root.setLevel(logging.DEBUG)
```

## Function Timing Decorators

Log function execution time automatically:

```python
from logust.contrib import log_fn, debug_fn

@log_fn
def process_data(items):
    # ... processing ...
    return result

process_data([1, 2, 3])
# Logs: "Called process_data with elapsed_time=0.123"

@debug_fn
async def fetch_user(user_id):
    return await db.get_user(user_id)

await fetch_user(123)
# Logs at DEBUG: "Called fetch_user with elapsed_time=0.050"
```

### Features

- Supports both sync and async functions
- `log_fn` logs at INFO level
- `debug_fn` logs at DEBUG level (only appears when DEBUG is enabled)
- Minimal overhead when log level is disabled

### Custom Log Level

```python
from logust.contrib import log_fn

@log_fn(level="WARNING")
def slow_operation():
    # This will log at WARNING level
    pass
```

## FastAPI / Starlette Middleware

Automatic request/response logging for web applications:

```python
from fastapi import FastAPI
from logust.contrib import RequestLoggerMiddleware

app = FastAPI()
app.add_middleware(RequestLoggerMiddleware)

# All requests are now logged:
# "Request started: GET /users ip=127.0.0.1"
# "Request successful: GET /users status=200 time=0.0123s ip=127.0.0.1"
```

### Configuration Options

```python
app.add_middleware(
    RequestLoggerMiddleware,
    skip_routes=["/health", "/metrics"],      # Skip these routes
    skip_regexes=[r"^/docs", r"^/openapi"],   # Skip regex patterns
    include_request_body=True,                 # Log request bodies
    max_body_size=1000,                        # Truncate large bodies
    mask_sensitive_data=True,                  # Mask passwords, tokens, etc.
)
```

### One-Liner Setup

For the quickest setup, use `setup_fastapi`:

```python
from fastapi import FastAPI
from logust.contrib.starlette import setup_fastapi

app = FastAPI()
setup_fastapi(app, skip_routes=["/health"])

# This sets up:
# - Request/response logging
# - Standard logging redirected to logust
# - Request IDs in all log messages
```

### Request ID Access

Access the current request ID anywhere in your code:

```python
from logust.contrib.starlette import get_request_id

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    request_id = get_request_id()
    logger.info(f"Processing request {request_id}")
    # ...
```

### Sensitive Data Masking

The middleware automatically masks common sensitive fields:

- password, passwd
- token, access_token, refresh_token, jwt
- secret, key, api_key
- authorization, credential

```python
# Request body: {"username": "john", "password": "secret123"}
# Logged as:    {"username": "john", "password": "***"}
```

## Complete Example

Here's a complete FastAPI application with all integrations:

```python
from fastapi import FastAPI
from logust import logger
from logust.contrib import intercept_logging, log_fn
from logust.contrib.starlette import setup_fastapi

# Create app
app = FastAPI()

# One-liner logust setup
setup_fastapi(app, skip_routes=["/health"])

# Add file logging
logger.add("app.log", rotation="daily", retention="7 days")
logger.add("app.json", serialize=True)

@log_fn
async def get_user_from_db(user_id: int):
    # Simulated DB call
    return {"id": user_id, "name": "John"}

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return await get_user_from_db(user_id)

@app.get("/health")
async def health():
    return {"status": "ok"}  # Not logged (skipped)
```

Output:
```
2025-01-01 12:00:00.123 | INFO     | Request started: GET /users/1 ip=127.0.0.1
2025-01-01 12:00:00.125 | INFO     | Called get_user_from_db with elapsed_time=0.002
2025-01-01 12:00:00.126 | INFO     | Request successful: GET /users/1 status=200 time=0.003s ip=127.0.0.1
```

## Requirements

The base `logust.contrib` module has no extra dependencies. For web framework integrations:

```bash
# For FastAPI/Starlette middleware
pip install starlette
# or
pip install fastapi
```
