# First Steps { #first-steps }

The simplest Logust program could look like this:

```python
--8<-- "docs_src/first_steps/tutorial001.py"
```

Copy that to a file `main.py`.

Run it:

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:06.708</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">3</font> - Hello, Logust!
```

</div>

That's it. No `basicConfig()`, no handler classes, no formatter objects. 😎

You imported a module, called a function, and you got a nicely formatted, colored log line.

## The default format { #the-default-format }

Let's look at that line piece by piece:

```
2026-10-06 12:01:06.708 | INFO     | __main__:<module>:3 - Hello, Logust!
```

* `2026-10-06 12:01:06.708`: the local **time** the message was logged, with milliseconds.
* `INFO    `: the **level** of the message, padded to 8 characters so that messages line up.
* `__main__`: the **name** of the module that logged the message. Your script runs as `__main__`. In a package, you would see something like `myapp.db`.
* `<module>`: the **function** that logged the message. `<module>` means "top-level code, not inside a function".
* `3`: the **line** number of the logging call.
* `Hello, Logust!`: your **message**.

Behind the scenes, that layout is the **format string**:

```
{time} | {level:<8} | {name}:{function}:{line} - {message}
```

Each `{...}` is a field that is filled in for every message. You will learn how to write your own format in [Formatting](formatting.md).

/// tip

The time, the module, the function and the line are collected for you. You don't need to pass `__name__` around or create one logger per module.

///

## Use `logger` { #use-logger }

Calling `logust.info()` is handy for a quick script. In an application you will normally import the **logger** object instead:

```python hl_lines="1 3-4"
--8<-- "docs_src/first_steps/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:06.772</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">3</font> - Hello, Logust!
<font color="#8A8A8A">2026-10-06 12:01:06.773</font> | <font color="#C4A000"><b>WARNING </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">4</font> - Disk usage is high
```

</div>

`logger` is the **one and only** logger of your application. There is nothing to create or configure: every module that does `from logust import logger` gets the same object.

The module-level functions are just shortcuts to it. `logust.info(...)` and `logger.info(...)` do exactly the same thing, and `logust.logger is logger` is `True`.

So, which one should you use?

* `from logust import logger`: recommended. The `logger` object has the whole API: logging methods, but also `add()`, `remove()`, `bind()`, `catch()`, and more.
* `import logust` + `logust.info(...)`: fine for small scripts and one-liners.

/// note | Coming from loguru?

It's the same idea as `from loguru import logger`. In most code, migrating is changing that import. See [Migrate from loguru](../how-to/migrate-from-loguru.md).

///

## Log from functions { #log-from-functions }

Now let's log from inside a function:

```python hl_lines="4-6 9"
--8<-- "docs_src/first_steps/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:06.835</font> | <font color="#3465A4"><b>DEBUG   </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">connect</font>:<font color="#06989A">5</font> - Connecting...
<font color="#8A8A8A">2026-10-06 12:01:06.836</font> | <font color="#8AE234"><b>SUCCESS </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">connect</font>:<font color="#06989A">6</font> - Connected
<font color="#8A8A8A">2026-10-06 12:01:06.836</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">10</font> - Ready
```

</div>

Notice that the function column now says `connect` for the first two messages. Logust looked up where each call came from, so you can tell at a glance which code produced which line.

You also used two more **levels**: `debug()` and `success()`. Each one has its own color. You will see all of them in the next chapter, [Log Levels](log-levels.md).

## The default handler { #the-default-handler }

Where did those lines go? 🤔

When you import Logust, the `logger` already has one **handler** set up for you, the **default handler**. It:

* Writes to the console, on **standard error** (`sys.stderr`), like loguru.
* Uses the default format you saw above.
* Uses colors when standard error is a terminal, and plain text when it is piped or redirected to a file. It follows the same rules as the handlers you add yourself, `NO_COLOR` and `FORCE_COLOR` included. See [Colors](sinks.md#colors).
* Shows every message from `DEBUG` up. `TRACE` messages are hidden.

/// tip

Because the logs go to standard error, `python main.py > out.txt` keeps them on your terminal and only puts your program's own output (`print()`) in the file. To save the logs, redirect standard error: `python main.py 2> logs.txt`.

///

/// info

Before Logust 0.6, the default handler wrote to standard output, always with colors. If you want your logs on standard output, replace the default handler with your own, as you will see in [Handlers and Sinks](sinks.md#replace-the-default-handler):

```python
import sys

from logust import logger

logger.remove()
logger.add(sys.stdout)
```

///

A handler takes messages and sends them somewhere: the console, a file, or any Python function. You can add as many as you want, each with its own level and format. You will do exactly that in [Handlers and Sinks](sinks.md) and [Logging to Files](file-output.md).

## Recap { #recap }

* `import logust` and call `logust.info()`, or, better, `from logust import logger` and call `logger.info()`.
* There is a single `logger` for the whole application, shared by every module.
* Each line shows the time, the level, the module, the function, the line and the message.
* The **default handler** writes to standard error, from `DEBUG` up, with colors on a terminal.
