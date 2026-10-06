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

The values are context-local, as in loguru: they live in a
[`contextvars`](https://docs.python.org/3/library/contextvars.html) variable, so each thread
and each asyncio task sees only the blocks it entered itself (or inherited from the task
that started it), and concurrent requests never pick up each other's values.

```python
async def handle(request_id: str) -> None:
    with logger.contextualize(request_id=request_id):
        logger.info("start")           # request_id of this task only
        await asyncio.sleep(0.1)
        logger.info("done")            # still this task's request_id

await asyncio.gather(handle("a"), handle("b"))
```

Inside the block, every logger sees the values: the logger the block was opened on, loggers
created with `bind()`, and the module-level functions (`logust.info(...)`). The block yields
the logger it was opened on, so `with logger.contextualize(...) as log:` works too.

### Nested contexts

Nested blocks merge their values; a key set again is overridden until the inner block
exits, and each block restores the previous values when it exits (also when an exception
leaves it).

```python
with logger.contextualize(user_id="123"):
    logger.info("User context")

    with logger.contextualize(action="login"):
        logger.info("Both user_id and action")

    logger.info("Only user_id")
```

### Precedence

Values from different sources merge into `extra` in loguru's order; later sources win:

1. `contextualize()` values of the current thread or task
2. `bind()` values of the logger (and `configure(extra=...)`)
3. The message's own keyword arguments (`logger.info("msg", key=value)`)

```python
with logger.contextualize(user="ctx"):
    logger.bind(user="bound").info("...")        # extra: {'user': 'bound'}
    logger.info("...", user="kw")                # extra: {'user': 'kw'}
```

### Threads, tasks and generators

- An asyncio task created inside a block inherits the values (asyncio copies the context
  when it starts a task) and keeps them even after the block exits. Blocks it opens itself
  do not affect its parent.
- A new `threading.Thread` starts without the values unless Python copies the context for
  it (`sys.flags.thread_inherit_context`, on by default on free-threaded builds). To carry
  them over, run the thread's target with `contextvars.copy_context().run(...)`.
- A generator runs in its caller's context, so a block left open across a `yield` stays
  visible to the caller until the generator resumes and exits it, as with loguru.
- A plain `logger.info("msg")` inside a block stays on the Rust fast path: the merged
  context is cached per thread, so logging inside a block costs the same as outside.

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

Changes a patcher makes to `record["message"]`, `record["extra"]` and `record["exception"]`
are used for the log call. Changes to other keys are ignored.

## The record dict

Filters (`add(..., filter=...)`), patchers, and callbacks (`add_callback()`) receive a
record dict shaped like loguru's, so ported loguru filters work:

```python
logger.add("warnings.log", filter=lambda r: r["level"].no >= 30 and r["time"].year > 2000)
logger.add("app.log", filter=lambda r: r["file"].name != "noisy.py")
```

| Key | Value |
|-----|-------|
| `level` | Level name. A `str`, so `record["level"] == "INFO"` works, with loguru's `.name`, `.no` and `.icon` |
| `level_no` | Numeric level (same as `record["level"].no`) |
| `message` | The message |
| `time` | Aware `datetime` of the record |
| `timestamp` | The same time as an RFC 3339 string |
| `elapsed` | `timedelta` since the logger started. `str()` and `{elapsed}` give `HH:MM:SS.mmm` |
| `name` | Module `__name__` of the caller |
| `module` | Caller file name without its extension |
| `function`, `line` | Caller function and line |
| `file` | Caller file basename. A `str` with loguru's `.name` and `.path` |
| `thread`, `process` | Objects with `.id` and `.name` |
| `thread_name`, `thread_id`, `process_name`, `process_id` | The same values as flat keys |
| `exception` | The formatted traceback text, or `None` |
| `extra` | Bound context and extra keyword arguments |

Bound values are also copied to the top level of the record (`record["user_id"]`), unless the
name is one of the keys above.

Differences from loguru:

- `record["exception"]` is the traceback text, not loguru's `(type, value, traceback)` tuple.
  Test it with `record["exception"] is not None` or search the text.
- The patcher record has no caller fields (`name`, `module`, `function`, `line`, `file`); they
  are collected after the patchers run. Its `time`, `timestamp`, `elapsed`, `thread` and
  `process` are computed when a patcher first reads them (or iterates the record), so patchers
  that only touch `record["extra"]` don't pay for them; `time` is the moment of that first read.
- `time`, `elapsed`, `thread` and `process` are not JSON-serializable. A callback that passes
  the whole record to `json.dumps()` should pick the keys it needs, or use `default=str`.
- The `level`, `file`, `thread` and `process` values are shared between records, so their
  attributes are read-only.

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
