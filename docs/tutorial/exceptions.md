# Logging Exceptions { #logging-exceptions }

Things go wrong. When they do, the most useful thing a log can have is the **traceback**: the exact chain of calls that led to the error.

Logust gives you three ways to get it into your logs:

* `logger.exception()` inside an `except` block.
* `logger.opt(exception=True)` when you want another level.
* `logger.catch()`, a decorator and context manager that catches and logs for you.

## `logger.exception()` { #logger-exception }

Call `logger.exception()` inside an `except` block:

```python hl_lines="11"
--8<-- "docs_src/exceptions/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:02:28.972 | ERROR    | __main__:<module>:11 - Could not compute the average
Traceback (most recent call last):
  File "/home/user/project/main.py", line 9, in <module>
    result = average([])
  File "/home/user/project/main.py", line 5, in average
    return sum(values) / len(values)
           ~~~~~~~~~~~~^~~~~~~~~~~~~
ZeroDivisionError: division by zero

```

</div>

You get a normal record at the `ERROR` level, followed by the full traceback of the exception being handled, exactly as Python would print it.

Logust finds the exception by itself (from `sys.exc_info()`), so you don't need to pass it. And your program keeps running: the exception was handled by your `except` block, Logust only logged it.

/// tip

Use `except SomeError:` or `except Exception:`, not a bare `except:`. A bare `except:` also catches `KeyboardInterrupt` and `SystemExit`, so your program would ignore Ctrl+C.

///

/// info

In a [JSON sink](json-output.md#exceptions-in-json), the traceback goes into the `exception` key, as one string. And if you want to choose where the traceback is written in a text format, use the `{exception}` token, see [Exceptions in the format](formatting.md#exceptions-in-the-format).

///

## Other levels with `opt(exception=True)` { #other-levels-with-opt-exception-true }

`logger.exception()` always logs at `ERROR`. Sometimes an exception is expected and a warning is enough. Use `logger.opt(exception=True)` and then any level method:

```python hl_lines="11"
--8<-- "docs_src/exceptions/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:02:29.069 | WARNING  | __main__:<module>:11 - No cache yet, starting empty
Traceback (most recent call last):
  File "/home/user/project/main.py", line 9, in <module>
    load_cache()
    ~~~~~~~~~~^^
  File "/home/user/project/main.py", line 5, in load_cache
    raise FileNotFoundError("cache.json")
FileNotFoundError: cache.json

```

</div>

`opt()` has more options for a single message. You will see them in [The opt() Method](../advanced/opt.md).

/// note

A plain `logger.error("...")` inside an `except` block does **not** add the traceback. Only `logger.exception()`, `opt(exception=True)` and `logger.catch()` do.

///

## The `catch()` decorator { #the-catch-decorator }

Writing `try` / `except` / `logger.exception()` everywhere gets repetitive. With `@logger.catch`, any exception that escapes the function is logged for you:

```python hl_lines="4"
--8<-- "docs_src/exceptions/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:02:35.691 | ERROR    | __main__:<module>:9 - An error occurred: division by zero
Traceback (most recent call last):
  File "/home/user/project/main.py", line 6, in divide
    return a / b
           ~~^~~
ZeroDivisionError: division by zero

divide() returned None
```

</div>

A few things happened here:

* The exception was logged at `ERROR`, with the message `"An error occurred: "` followed by the exception message.
* The record points at the **caller** of `divide()` (line 9), the place where the error hit your program. The traceback shows where it was raised.
* The exception was **suppressed**: `divide()` returned `None` and the program went on.

That makes `@logger.catch` perfect for the "main" function of a script, a thread target, or a background job: nothing crashes silently anymore. 🚨

/// tip

`@logger.catch` works with or without parentheses, and also on `async def` functions and generator functions: the exception is caught when the coroutine is awaited or the generator is iterated.

///

## The `catch()` context manager { #the-catch-context-manager }

You don't need a whole function. `logger.catch()` also works as a context manager, for a block of code:

```python hl_lines="5"
--8<-- "docs_src/exceptions/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:02:29.230 | ERROR    | __main__:<module>:5 - Could not read the port: 'port'
Traceback (most recent call last):
  File "/home/user/project/main.py", line 6, in <module>
    port = int(config["port"])
               ~~~~~~^^^^^^^^
KeyError: 'port'

2026-10-06 12:02:29.230 | INFO     | __main__:<module>:8 - The program goes on
```

</div>

The record points at the `with` line, and `message=` replaced the default `"An error occurred"`.

## `catch()` options { #catch-options }

You can tune what is caught and what happens next. Here is a function that parses user input, where a bad value is expected and not worth an `ERROR`:

```python hl_lines="4"
--8<-- "docs_src/exceptions/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

42
2026-10-06 12:02:35.775 | WARNING  | __main__:<module>:10 - Bad input: invalid literal for int() with base 10: 'forty-two'
Traceback (most recent call last):
  File "/home/user/project/main.py", line 6, in parse_age
    return int(text)
ValueError: invalid literal for int() with base 10: 'forty-two'

-1
```

</div>

* The first argument, `ValueError`, is the exception type to catch. Any other exception propagates untouched, without being logged. Pass a tuple to catch several types: `logger.catch((ValueError, TypeError))`.
* `level="WARNING"` sets the level of the record. A level name or a number.
* `message="Bad input"` replaces the beginning of the message.
* `default=-1` is what the decorated function returns when an exception was caught, instead of `None`.

### Re-raise after logging { #re-raise-after-logging }

Sometimes you want the log, but the caller still has to know that it failed. Use `reraise=True`:

```python hl_lines="4"
--8<-- "docs_src/exceptions/tutorial006.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:02:35.847 | ERROR    | __main__:<module>:10 - An error occurred: payment gateway timed out
Traceback (most recent call last):
  File "/home/user/project/main.py", line 6, in charge
    raise ConnectionError("payment gateway timed out")
ConnectionError: payment gateway timed out

The caller can still handle it
```

</div>

The exception is logged, then raised again, so the `except` in the caller still runs.

### Exclude some exceptions and react to errors { #exclude-some-exceptions-and-react-to-errors }

`exclude=` lists exception types that should pass through **without** being logged. And `onerror=` is a function that is called with the exception, after it is logged:

```python hl_lines="8"
--8<-- "docs_src/exceptions/tutorial007.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:02:35.917 | ERROR    | __main__:<module>:13 - An error occurred: database is down
Traceback (most recent call last):
  File "/home/user/project/main.py", line 10, in main
    raise RuntimeError("database is down")
RuntimeError: database is down

Alerting on-call: RuntimeError('database is down')
```

</div>

A common pattern for scripts is `onerror=lambda exc: sys.exit(1)`, so the process still exits with an error code after the failure is logged.

### All the options { #all-the-options }

| Option | Default | Description |
|--------|---------|-------------|
| `exception` | `Exception` | Exception type(s) to catch (first positional argument) |
| `level` | `"ERROR"` | Level name or number of the record |
| `reraise` | `False` | Raise the exception again after logging it |
| `onerror` | `None` | Called with the exception after it is logged |
| `exclude` | `None` | Exception type(s) that propagate without being logged |
| `default` | `None` | Return value of the decorated function when an exception is caught |
| `message` | `"An error occurred"` | Message prefix; the record reads `"<message>: <exception>"` |

/// note | Technical Details

The exception message is never parsed as [color markup](formatting.md#colors), so an exception like `ValueError("<b>bad</b>")` is logged as is.

Logust's own frames, like the wrapper added by `@logger.catch`, are left out of the traceback.

///

## More traceback detail { #more-traceback-detail }

By default, tracebacks look exactly like Python's. Each sink can also show the frames **above** the point where the exception was caught, and the **values of the variables** on each line, which is a huge help when debugging. These are the `backtrace=` and `diagnose=` options, covered in [Tracebacks](../advanced/tracebacks.md).

And if you want to send errors to a monitoring service like Sentry, have a look at [Callbacks](../advanced/callbacks.md).

## Recap { #recap }

* `logger.exception("...")` in an `except` block logs at `ERROR` with the full traceback.
* `logger.opt(exception=True).warning("...")` does the same at any level.
* `@logger.catch` logs any exception that escapes a function, and suppresses it. `with logger.catch():` does the same for a block.
* `catch()` options choose what is caught (`exception`, `exclude`), how it is logged (`level`, `message`) and what happens next (`reraise`, `default`, `onerror`).

Next, let's choose exactly which records each sink receives: [Filtering Records](filters.md).
