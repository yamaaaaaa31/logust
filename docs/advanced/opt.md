# Per-message Options with opt() { #per-message-options-with-opt }

Handlers decide how **all** messages are written. But sometimes you want to change how **one** message is logged: attach the current exception, skip an expensive computation, or point the record at a different caller.

That's what `logger.opt()` does. It returns a logger with the options you pass, for the next call:

```python
logger.opt(lazy=True).debug("Rows: {}", count_rows)
```

`opt()` supports these options:

| Option | Default | What it does |
|--------|---------|--------------|
| `lazy` | `False` | Call function arguments only if the message is going to be logged. |
| `exception` | `False` | Attach the exception currently being handled. |
| `depth` | `0` | Report a caller further up the stack. |
| `capture` | `True` | `False` keeps keyword arguments out of `extra`. |
| `colors` | `None` | `False` keeps color markup in the message as plain text. |
| `backtrace` | `False` | Show the frames above the catch point in the traceback. |
| `diagnose` | `False` | Show variable values in the traceback. |

Let's see them one by one.

## Lazy evaluation { #lazy-evaluation }

Python evaluates the arguments of a function **before** calling it. So in `logger.debug("Rows: {}", count_rows())`, `count_rows()` runs even when debug messages are hidden. If it's slow, you pay for it on every call, for nothing.

With `opt(lazy=True)`, you pass the **function itself** (without calling it), and Logust calls it only if the message will be logged:

```python hl_lines="14-16"
--8<-- "docs_src/advanced_opt/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

  counting rows... (slow)
  counting rows... (slow)
INFO  | Rows: 1000000
```

</div>

The handler shows `INFO` and above, so none of the `DEBUG` messages are written. But:

* Line 14 still counts the rows (the first "counting rows...") and throws the result away. 😱
* Line 15 passes `count_rows` without parentheses. The message is hidden, so `count_rows` is never called. 🎉
* Line 16 is shown, so `count_rows` is called, and its result goes in the message.

With `lazy=True`, every **positional** argument that is callable is called. Keyword arguments are passed as is.

/// tip

If you need to do more work than one function call, check the level first with `logger.is_level_enabled("DEBUG")`. See [Log Levels](../tutorial/log-levels.md).

///

## Attach the current exception { #attach-the-current-exception }

`logger.exception()` logs at `ERROR` with the traceback. But what if a caught exception is only a **warning** for you? Use `opt(exception=True)` with any level:

```python hl_lines="16"
--8<-- "docs_src/advanced_opt/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

WARNING | No config file, using the defaults
Traceback (most recent call last):
  File "/home/user/project/main.py", line 14, in <module>
    load_config("settings.toml")
    ~~~~~~~~~~~^^^^^^^^^^^^^^^^^
  File "/home/user/project/main.py", line 10, in load_config
    raise FileNotFoundError(path)
FileNotFoundError: settings.toml
```

</div>

`opt(exception=True)` attaches the exception that is being handled, so call it inside an `except` block. Outside of one, the message is logged without a traceback.

## Report a different caller { #report-a-different-caller }

Every record knows the function and line that logged it. But if you wrap the logger in a helper function, the record points at the **helper**, which is usually not what you want.

`opt(depth=1)` tells Logust to go **one frame up** the stack, to the code that called your helper:

```python hl_lines="14"
--8<-- "docs_src/advanced_opt/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

log_step:10 | Importing users
import_users:19 | Importing users
```

</div>

The first line points at `log_step`, which is not very useful. The second points at `import_users`, line 19: where the step actually happened. 🤓

Use `depth=2` if there are two helper functions in between, and so on.

## Keep keyword arguments out of extra { #keep-keyword-arguments-out-of-extra }

As you saw in [Message Arguments](../tutorial/message-arguments.md), keyword arguments that are not used by the message go to `extra`. With `opt(capture=False)` they are only used to format the message:

```python hl_lines="9"
--8<-- "docs_src/advanced_opt/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

User alice logged in | extra={'ip': '10.0.0.7'}
User alice logged in | extra={}
```

</div>

## Keep markup as plain text { #keep-markup-as-plain-text }

Logust understands color tags like `<red>...</red>` in messages (see [Formatting](../tutorial/formatting.md#colors-in-messages)). That's great for your own messages, but not for text that comes from somewhere else, like user input. Tags in it would be interpreted, or removed.

`opt(colors=False)` keeps the markup of that message as plain text:

```python hl_lines="11"
--8<-- "docs_src/advanced_opt/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

Comment posted: hello
Comment posted: <b>hello</b>
```

</div>

The first line lost the `<b>` tags. The second one shows exactly what the user wrote.

/// note | Technical Details

loguru only parses color markup with `opt(colors=True)`. Logust always parses it, so `colors=True` changes nothing, and `colors=False` is the way to turn it off for one message.

///

## Tracebacks with more detail { #tracebacks-with-more-detail }

`opt(backtrace=True)` and `opt(diagnose=True)` add more detail to the traceback of one message: the frames above the catch point, and the values of the variables. They are covered in [Tracebacks](tracebacks.md#enhanced-diagnostics-for-one-message).

Both of them also attach the current exception, so you don't need `exception=True` with them.

## Combining options { #combining-options }

You can pass several options at once:

```python
logger.opt(lazy=True, depth=1).debug("State: {}", dump_state)
```

The logger returned by `opt()` has the level methods (`trace()` to `critical()`) and `log()`, so it works with [custom levels](custom-levels.md) too:

```python
logger.opt(lazy=True).log("NOTICE", "Rows: {}", count_rows)
```

/// info

`opt()` returns a logger for **logging**, not a full logger: it doesn't have `bind()`, `add()` or `exception()`. Call `opt()` last, right before the logging method: `logger.bind(user="alice").opt(lazy=True).info(...)`.

///

Some loguru options, `opt(raw=True)` and `opt(record=True)`, are not supported yet.

## Recap { #recap }

* `logger.opt(...)` changes how **one** message is logged.
* `lazy=True` calls function arguments only when the message is written.
* `exception=True` attaches the current exception at any level.
* `depth=1` points the record at the caller of your helper function.
* `capture=False` keeps keyword arguments out of `extra`.
* `colors=False` keeps color tags as plain text.
* `backtrace=True` and `diagnose=True` add traceback detail for one message.
