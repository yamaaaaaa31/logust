"""Function timing decorators for logust.

This module provides decorators that automatically log function execution
time, supporting both sync and async functions.

Example:
    >>> from logust.contrib import log_fn, debug_fn
    >>>
    >>> @log_fn
    ... def process_data(items):
    ...     # ... processing ...
    ...     return result
    >>>
    >>> process_data([1, 2, 3])
    # Logs: "Called process_data with elapsed_time=0.123"
    >>>
    >>> @debug_fn
    ... async def fetch_data():
    ...     # ... async fetch ...
    ...     return data
    >>>
    >>> await fetch_data()
    # Logs at DEBUG level: "Called fetch_data with elapsed_time=0.456"
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from functools import wraps
from time import perf_counter
from typing import Any, TypeVar, overload

F = TypeVar("F", bound=Callable[..., Any])


def _get_callable_name(fn: Any) -> str:
    """Get the name of a callable.

    Args:
        fn: A callable object.

    Returns:
        The name of the callable.
    """
    return getattr(fn, "__name__", None) or getattr(fn, "__qualname__", None) or repr(fn)


@overload
def log_fn(fn: F) -> F: ...


@overload
def log_fn(*, level: str = ...) -> Callable[[F], F]: ...


def log_fn(
    fn: F | None = None,
    *,
    level: str = "INFO",
) -> F | Callable[[F], F]:
    """Decorator that logs function execution time at INFO level.

    Supports both sync and async functions. Logs the function name
    and elapsed time after execution completes.

    Can be used with or without parentheses:
        >>> @log_fn
        ... def my_func(): ...

        >>> @log_fn(level="DEBUG")
        ... def my_func(): ...

    Args:
        fn: The function to wrap (when used without parentheses).
        level: Log level to use (default: "INFO").

    Returns:
        Wrapped function that logs execution time.

    Example:
        >>> from logust.contrib import log_fn
        >>>
        >>> @log_fn
        ... def calculate(x, y):
        ...     return x + y
        >>>
        >>> calculate(1, 2)
        # Logs: "Called calculate with elapsed_time=0.001"
        >>>
        >>> @log_fn
        ... async def fetch_user(user_id):
        ...     return await db.get_user(user_id)
        >>>
        >>> await fetch_user(123)
        # Logs: "Called fetch_user with elapsed_time=0.050"
    """

    def decorator(func: F) -> F:
        fn_name = _get_callable_name(func)

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                from logust import logger

                start = perf_counter()
                result = await func(*args, **kwargs)
                elapsed = perf_counter() - start
                logger.opt(depth=1).log(level, f"Called {fn_name} with elapsed_time={elapsed:.3f}")
                return result

            return async_wrapper  # type: ignore[return-value]

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from logust import logger

            start = perf_counter()
            result = func(*args, **kwargs)
            elapsed = perf_counter() - start
            logger.opt(depth=1).log(level, f"Called {fn_name} with elapsed_time={elapsed:.3f}")
            return result

        return wrapper  # type: ignore[return-value]

    if fn is not None:
        return decorator(fn)
    return decorator


@overload
def debug_fn(fn: F) -> F: ...


@overload
def debug_fn() -> Callable[[F], F]: ...


def debug_fn(fn: F | None = None) -> F | Callable[[F], F]:
    """Decorator that logs function execution time at DEBUG level.

    This is a convenience wrapper around log_fn with level="DEBUG".
    Useful for detailed timing information that should only appear
    when debug logging is enabled.

    Args:
        fn: The function to wrap.

    Returns:
        Wrapped function that logs execution time at DEBUG level.

    Example:
        >>> from logust.contrib import debug_fn
        >>>
        >>> @debug_fn
        ... def internal_process(data):
        ...     # detailed processing
        ...     return result
        >>>
        >>> internal_process(data)
        # Logs at DEBUG: "Called internal_process with elapsed_time=0.005"
    """
    if fn is not None:
        return log_fn(fn, level="DEBUG")  # type: ignore[call-overload, no-any-return]
    return log_fn(level="DEBUG")
