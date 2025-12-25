#!/usr/bin/env python3
"""Exception handling example - Logging exceptions with tracebacks.

This example demonstrates various ways to capture and log exceptions.
"""

from logust import logger


def divide(a: int, b: int) -> float:
    """A function that might raise an exception."""
    return a / b


def risky_operation() -> None:
    """A function that has multiple failure points."""
    data = {"key": "value"}
    _ = data["missing_key"]  # KeyError


# 1. Using the catch() decorator - most convenient
@logger.catch(ZeroDivisionError, level="ERROR")
def decorated_divide(a: int, b: int) -> float:
    """Division with automatic exception catching."""
    return a / b


@logger.catch(reraise=True)
def decorated_with_reraise() -> None:
    """Exception is logged AND re-raised."""
    raise ValueError("This will be logged and re-raised")


# 2. Using exception() method - for try/except blocks
def manual_exception_logging() -> None:
    """Manually log exceptions in try/except."""
    try:
        result = divide(10, 0)
        print(f"Result: {result}")
    except ZeroDivisionError:
        logger.exception("Division failed")  # Logs ERROR with traceback


# 3. Using opt(exception=True) - for current exception context
def opt_exception_logging() -> None:
    """Using opt() to capture current exception."""
    try:
        risky_operation()
    except KeyError:
        logger.opt(exception=True).error("Key not found in dictionary")


# 4. Using opt(diagnose=True) - shows variable values
def diagnose_example() -> None:
    """Using diagnose to show variable values in traceback."""
    try:
        x = 10
        y = 0
        z = "some context"  # noqa: F841
        result = x / y  # noqa: F841
    except ZeroDivisionError:
        # diagnose=True will show: x=10, y=0, z="some context"
        logger.opt(diagnose=True).error("Calculation failed with diagnose")


# 5. Using opt(backtrace=True) - extended stack trace
def outer_function() -> None:
    """Outer function in call stack."""
    inner_function()


def inner_function() -> None:
    """Inner function where exception occurs."""
    try:
        raise RuntimeError("Deep error")
    except RuntimeError:
        # backtrace=True shows the full call stack
        logger.opt(backtrace=True).error("Error with full backtrace")


def main() -> None:
    print("=== 1. Using @logger.catch() decorator ===\n")
    result = decorated_divide(10, 0)
    print(f"Decorated divide returned: {result}")

    print("\n=== 2. Using logger.exception() ===\n")
    manual_exception_logging()

    print("\n=== 3. Using logger.opt(exception=True) ===\n")
    opt_exception_logging()

    print("\n=== 4. Using logger.opt(diagnose=True) ===\n")
    diagnose_example()

    print("\n=== 5. Using logger.opt(backtrace=True) ===\n")
    outer_function()

    print("\n=== 6. Catch with reraise ===\n")
    try:
        decorated_with_reraise()
    except ValueError as e:
        print(f"Caught re-raised exception: {e}")


if __name__ == "__main__":
    main()
