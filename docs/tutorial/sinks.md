# Handlers and Sinks { #handlers-and-sinks }

So far, every message went to the [default handler](first-steps.md#the-default-handler). Now let's choose where messages go.

In Logust, a **handler** is a destination for log messages, with its own settings: a minimum level, a format, colors, and more. The destination itself is called the **sink**. It can be:

* A **stream**, like `sys.stdout` or `sys.stderr`.
* A **file path**, covered in the next chapter, [Logging to Files](file-output.md).
* Any **Python callable** that accepts a string.

Each message is sent to every handler whose level lets it through.

## Add a handler { #add-a-handler }

You add a handler with `logger.add()`, passing the sink as the first argument:

```python hl_lines="5"
--8<-- "docs_src/sinks/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

New handler id: 1
<font color="#8A8A8A">2026-10-06 12:01:07.721</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">8</font> - Sent to both handlers
stderr | <font color="#4E9A06"><b>INFO</b></font> | Sent to both handlers
<font color="#8A8A8A">2026-10-06 12:01:07.721</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">11</font> - Sent to the default handler only
```

</div>

The first message went to **both** handlers, the default one and the new one, with its own short format. Both write to standard error.

The `format` argument is the same kind of format string you saw in [First Steps](first-steps.md#the-default-format). [Formatting](formatting.md) shows every field you can use.

## Remove a handler { #remove-a-handler }

`logger.add()` returns an integer, the **handler ID**. Keep it if you want to remove that handler later:

```python hl_lines="5 10"
--8<-- "docs_src/sinks/tutorial001.py"
```

`logger.remove(handler_id)` removes just that handler. That's why the last message only went to the default handler.

`remove()` returns `True` if a handler was removed, and `False` if there was no handler with that ID.

## Replace the default handler { #replace-the-default-handler }

Call `logger.remove()` **without** an ID to remove **all** the handlers, including the default one. This is the usual way to start your own configuration from a clean slate:

```python hl_lines="5-6"
--8<-- "docs_src/sinks/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">12:01:07</font> | <font color="#4E9A06"><b>INFO    </b></font> | Server starting
<font color="#8A8A8A">12:01:07</font> | <font color="#C4A000"><b>WARNING </b></font> | Cache is almost full
```

</div>

Now there is a single handler, with your format. The default handler is gone for good, so messages are not shown twice.

/// tip

Configure your handlers **once**, when your application starts, for example in your `main.py`. The rest of your code just does `from logust import logger` and logs.

///

## Colors { #colors }

The `colorize` argument controls the ANSI color codes:

```python
logger.add(sys.stdout)                  # Colors only when writing to a terminal
logger.add(sys.stdout, colorize=True)   # Always colors
logger.add(sys.stdout, colorize=False)  # Never colors
```

By default (`colorize=None`), Logust does the same detection as loguru: colors are used when the stream is a terminal, and not when the output is piped or redirected to a file. It also respects the `NO_COLOR` and `FORCE_COLOR` environment variables, and turns colors on in CI services, PyCharm and Jupyter.

So this handler never uses colors, even in a terminal:

```python hl_lines="6"
--8<-- "docs_src/sinks/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

INFO     | No colors, even in a terminal
```

</div>

/// info

The [default handler](first-steps.md#the-default-handler) uses the same detection for standard error. It decides once, when Logust is imported, so changing `NO_COLOR` or `FORCE_COLOR` later doesn't affect it.

///

## Callable sinks { #callable-sinks }

A sink can also be any **callable** that takes a string. Logust formats the message and calls it, once per message.

For example, `list.append`:

```python hl_lines="3 6"
--8<-- "docs_src/sinks/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

['INFO | First message', 'WARNING | Second message']
```

</div>

Notice the strings: they are fully formatted, and they **don't** end with a newline. With a file or a stream, Logust adds the newline. With a callable, what to do with the line is up to you.

Callable sinks don't use colors unless you pass `colorize=True`.

/// tip

A list sink like this one is a simple way to check your log messages in tests.

///

## A level per handler { #a-level-per-handler }

Each handler has its own minimum **level**, set with the `level` argument. Handlers you add start at `DEBUG` unless you say otherwise.

That makes callable sinks great for alerts. Here's a sink that only receives errors:

```python hl_lines="4-6 9"
--8<-- "docs_src/sinks/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:07.954</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">11</font> - Request handled
[on-call] ERROR: Payment provider is down
<font color="#8A8A8A">2026-10-06 12:01:07.954</font> | <font color="#CC0000"><b>ERROR   </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">12</font> - Payment provider is down
```

</div>

The `INFO` message only reached the console. The `ERROR` message reached both.

/// warning

Sinks are called **synchronously**, in the thread that logs. Keep them fast: a slow network call inside a sink slows down every `logger.error()`. `async def` functions are not accepted as sinks.

If a sink raises an exception, Logust drops the error silently by default. You can change that with `catch=`, see [Sink Errors](../advanced/sink-errors.md).

///

## Multiple handlers { #multiple-handlers }

Now let's put it all together: two console handlers, each with its own level and format:

```python hl_lines="6-7"
--8<-- "docs_src/sinks/tutorial006.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">12:01:08</font> | <font color="#4E9A06"><b>INFO    </b></font> | Shown on stdout
<font color="#8A8A8A">12:01:08</font> | <font color="#C4A000"><b>WARNING </b></font> | Shown on stdout and stderr
<font color="#C4A000"><b>WARNING</b></font>: Shown on stdout and stderr (<font color="#06989A">__main__</font>:<font color="#06989A">11</font>)
```

</div>

* `DEBUG` is below both levels, so it goes nowhere.
* `INFO` passes the `sys.stdout` handler only.
* `WARNING` passes both, and each handler formats it its own way.

A typical production setup combines the same idea with a file and [JSON output](json-output.md): human-readable lines on the console, and JSON in a file for your log platform.

/// note

[`set_level()`](log-levels.md#set-the-minimum-level) changes the level of **all** console handlers, the ones for `sys.stdout` and `sys.stderr` included. To give each one its own level, pass `level=` to `add()` as above.

///

## Other streams { #other-streams }

Any object with a `write()` method works as a stream sink, for example an `io.StringIO` or an open text file. Logust writes each formatted message followed by a newline, and calls `flush()` if the object has one.

```python
import io

buffer = io.StringIO()
logger.add(buffer, format="{message}")
```

The stream is captured when you call `add()`. If something replaces `sys.stdout` afterwards, the handler keeps writing to the original one.

## Recap { #recap }

* `logger.add(sink, ...)` adds a handler and returns its ID. A sink can be a stream, a file path, or a callable.
* `logger.remove(handler_id)` removes one handler, `logger.remove()` removes all of them, including the default one.
* `colorize=None` (the default) uses colors only on a terminal. `True` and `False` force them on or off.
* Callable sinks receive the formatted message, without a trailing newline.
* Each handler has its own `level` and `format`, and a message goes to every handler whose level lets it through.
