# Tracebacks { #tracebacks }

In the tutorial you learned to log exceptions with `logger.exception()`, `@logger.catch` and `opt(exception=True)` (see [Exceptions](../tutorial/exceptions.md)). They all write a traceback, the same one Python would print.

When you're debugging, a traceback can tell you even more: **what called** the code that caught the exception, and **what the values were** when it failed. Logust can add both, per handler or per message.

## More detail in one handler { #more-detail-in-one-handler }

Each handler decides how much a logged traceback shows, with two options of `logger.add()`:

| Option | Default | Adds |
|--------|---------|------|
| `backtrace` | `False` | The frames **above** the point where the exception was caught. |
| `diagnose` | `False` | The **values** of the local variables used on each line. |

A common setup is a short traceback on the console, and the full detail in a debug file:

```python hl_lines="6-7"
--8<-- "docs_src/advanced_tracebacks/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

ERROR | Could not compute the average
Traceback (most recent call last):
  File "/home/user/project/main.py", line 17, in report
    return average(values, skip=3)
  File "/home/user/project/main.py", line 12, in average
    return total / (len(values) - skip)
           ~~~~~~^~~~~~~~~~~~~~~~~~~~~~
ZeroDivisionError: division by zero

--- debug.log ---
ERROR | Could not compute the average
Traceback (most recent call last):
  File "/home/user/project/main.py", line 22, in <module>
    report([4, 8, 15])
    | report = <function report at 0x1033f9760>
  File "/home/user/project/main.py", line 17, in report
    return average(values, skip=3)
    | values = [4, 8, 15]
  File "/home/user/project/main.py", line 12, in average
    return total / (len(values) - skip)
    | values = [4, 8, 15]
    | skip = 3
    | total = 27
ZeroDivisionError: division by zero
```

</div>

Compare the two:

* The console traceback starts in `report()`, where the exception was **caught**. That's the standard Python behavior.
* With `backtrace=True`, the file also shows the frame **above** it: line 22, where `report()` was called. Very useful when the same function is called from many places.
* With `diagnose=True`, each line is followed by the variables it uses, as `| name = value`. Now you can see why it failed: `len(values) - skip` is `3 - 3`. 🤓

The options apply to every traceback a handler writes: from `exception()`, `catch()` and `opt(exception=True)`.

## Why both are off by default { #why-both-are-off-by-default }

/// warning | Different defaults from loguru

loguru defaults to `backtrace=True, diagnose=True`. Logust keeps both **off**.

`diagnose` writes variable **values** into your logs. Those values can be passwords, API tokens, or personal data, and logs are often shipped to places with wider access than your database. Turn `diagnose` on for development handlers only.

///

If you're porting from loguru and want the same output, pass `backtrace=True, diagnose=True` explicitly to the handlers that should have them.

## Enhanced diagnostics for one message { #enhanced-diagnostics-for-one-message }

Sometimes you don't want more detail everywhere, just for **one** tricky message. `opt()` accepts the same two options, and they apply to that message on **every** handler:

```python hl_lines="17"
--8<-- "docs_src/advanced_tracebacks/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

ERROR | Could not compute the average
Traceback (most recent call last):
  File "/home/user/project/main.py", line 15, in <module>
    average([4, 8, 15], skip=3)
    | average = <function average at 0x104c1cb80>
  File "/home/user/project/main.py", line 11, in average
    return total / (len(values) - skip)
    | values = [4, 8, 15]
    | skip = 3
    | total = 27
ZeroDivisionError: division by zero
```

</div>

The handler has neither option, but this one message shows the variable values.

The same goes for `opt(backtrace=True)`, to show the frames above the catch point:

```python
try:
    process_batch()
except Exception:
    logger.opt(backtrace=True).error("Batch failed")
```

`opt(backtrace=True)` and `opt(diagnose=True)` attach the current exception by themselves, you don't need `exception=True` too. And they add to the handler settings: a handler with `diagnose=True` keeps it.

/// info

`opt(backtrace=...)` and `opt(diagnose=...)` are Logust additions, loguru only has them on handlers.

///

## Good to know { #good-to-know }

* The traceback is formatted only when an exception is logged, once for each variant the handlers need. Messages without an exception don't pay anything for these options.
* [Patchers](records-and-patch.md) and [callbacks](callbacks.md) see the plain traceback text in `record["exception"]`.
* A traceback you pass yourself as text, with `logger.error("...", exception="...")`, is written as is by every handler.
* Logust's own frames (for example the wrapper added by `@logger.catch`) are left out of tracebacks.
* Tracebacks are not colorized. The style differs from loguru: `diagnose` lists the variables under each line instead of annotating the source, and `backtrace` adds the outer frames without loguru's `⥤` marker.

## Recap { #recap }

* `logger.add(..., backtrace=True)` shows the frames above the catch point.
* `logger.add(..., diagnose=True)` shows the variable values on each line.
* Both default to `False`, because `diagnose` can leak secrets into logs.
* `logger.opt(backtrace=True)` / `logger.opt(diagnose=True)` turn them on for one message.
