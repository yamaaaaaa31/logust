# Exception Handling

Pick the pattern that matches your flow.

!!! info "Three ways to log exceptions"
    `exception()` in try/except, `catch()` as decorator or context manager, or
    `opt(exception=True)` for control.

## Quick choices

=== "exception()"
    ```python
    from logust import logger

    try:
        result = 1 / 0
    except ZeroDivisionError:
        logger.exception("Division failed")
    ```

=== "catch()"
    ```python
    from logust import logger

    @logger.catch
    def risky_function():
        return 1 / 0

    risky_function()

    with logger.catch():
        1 / 0
    ```

=== "opt(exception=True)"
    ```python
    from logust import logger

    try:
        risky_operation()
    except Exception:
        logger.opt(exception=True).error("Operation failed")
    ```

!!! note
    Use `except Exception` instead of a bare `except` unless you need to catch
    `BaseException` (KeyboardInterrupt, SystemExit).

## exception() output

```
2025-12-24 12:00:00 | ERROR | Division failed
Traceback (most recent call last):
  File "example.py", line 4, in <module>
    result = 1 / 0
ZeroDivisionError: division by zero
```

## catch() options

`catch()` works with or without parentheses, as a decorator or as a context
manager. The record points at the caller of the decorated function, or at the
function containing the `with` block.

```python
from logust import logger

@logger.catch
def no_parentheses():
    raise ValueError("Caught with default options")

with logger.catch(message="Block failed"):
    raise ValueError("Caught and suppressed")

@logger.catch(reraise=True)
def must_succeed():
    raise ValueError("Failed")

@logger.catch(level="WARNING")
def might_fail():
    raise RuntimeError("Oops")

@logger.catch(message="Function failed")
def another_function():
    raise Exception("Error")

@logger.catch(exception=ValueError)
def validate():
    raise ValueError("Invalid")

@logger.catch(exception=(ValueError, TypeError))
def process():
    raise TypeError("Wrong type")

@logger.catch(default=-1)
def parse_int(text):
    return int(text)  # parse_int("x") logs and returns -1

@logger.catch(exclude=KeyboardInterrupt, onerror=lambda exc: sys.exit(1))
def main():
    ...
```

| Option | Default | Description |
|--------|---------|-------------|
| `exception` | `Exception` | Exception type(s) to catch |
| `level` | `"ERROR"` | Level name or number of the record |
| `reraise` | `False` | Re-raise after logging |
| `onerror` | `None` | Called with the exception after it is logged |
| `exclude` | `None` | Exception type(s) that propagate without being logged |
| `default` | `None` | Return value of the decorated function when an exception is caught |
| `message` | `"An error occurred"` | Message prefix; the record reads `"<message>: <exception>"` |

Coroutine functions and generator functions are supported: the exception is
caught when the coroutine is awaited or the generator is iterated.

## Enhanced diagnostics

Show variable values at each stack frame:

```python
try:
    a = 10
    b = 0
    result = a / b
except Exception:
    logger.opt(diagnose=True).error("Calculation failed")
```

Extended backtrace beyond the catch point:

```python
try:
    nested_function()
except Exception:
    logger.opt(backtrace=True).error("Deep error")
```

## Callbacks for error monitoring

```python
from logust import logger, LogLevel

def send_to_sentry(record):
    if record["level"] == "ERROR":
        # sentry_sdk.capture_message(record["message"])
        pass

logger.add_callback(send_to_sentry, level=LogLevel.Error)
```
