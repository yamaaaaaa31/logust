# Context Binding

Attach structured data to records without manual string formatting.

!!! tip "Best practice"
    Use `bind()` for request IDs, user IDs, and other metadata that should appear in every log.

## Overview

- `bind()` creates a new logger with permanent context.
- `contextualize()` adds temporary context in a `with` block.
- `patch()` modifies records dynamically before they are emitted.

## bind() - Permanent context

```python
from logust import logger

user_logger = logger.bind(user_id="123", session="abc")
user_logger.info("User action")
```

With JSON output, extra fields are included:

```json
{
  "time": "2025-12-24T12:00:00",
  "level": "INFO",
  "message": "User action",
  "extra": {
    "user_id": "123",
    "session": "abc"
  }
}
```

## contextualize() - Temporary context

```python
from logust import logger

with logger.contextualize(request_id="abc"):
    logger.info("Processing")
    logger.info("Done")

logger.info("Outside")
```

### Nested contexts

```python
with logger.contextualize(user_id="123"):
    logger.info("User context")

    with logger.contextualize(action="login"):
        logger.info("Both user_id and action")

    logger.info("Only user_id")
```

## patch() - Dynamic modification

```python
from logust import logger
import threading

def add_thread_info(record):
    record["extra"]["thread"] = threading.current_thread().name

patched_logger = logger.patch(add_thread_info)
patched_logger.info("Thread-aware log")
```

### Chaining patchers

```python
def add_request_id(record):
    record["extra"]["request_id"] = get_current_request_id()

def add_user_id(record):
    record["extra"]["user_id"] = get_current_user_id()

enhanced_logger = logger.patch(add_request_id).patch(add_user_id)
```

## Use cases

### Web request logging

```python
from logust import logger

def handle_request(request):
    req_logger = logger.bind(
        request_id=request.id,
        method=request.method,
        path=request.path,
    )

    req_logger.info("Request started")
    # ... process request ...
    req_logger.info("Request completed")
```

### User session logging

```python
def process_user_action(user, action):
    with logger.contextualize(user_id=user.id, action=action):
        logger.info("Processing action")
```
