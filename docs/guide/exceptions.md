# Exception Handling

Pick the pattern that matches your flow.

!!! info "Three ways to log exceptions"
    `exception()` in try/except, `@catch()` as decorator, or `opt(exception=True)` for control.

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

    @logger.catch()
    def risky_function():
        return 1 / 0

    risky_function()
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

```python
from logust import logger

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
```

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
