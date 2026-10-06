# Adding Context { #adding-context }

A message like `"Payment failed"` tells you *what* happened. But when you are debugging at 3 AM, you also want to know *for whom*, *in which request*, *for which order*.

You could put all of that in the message with f-strings. But then every message has to repeat it, and your log aggregator sees one opaque string.

Logust has a better way: attach **context** to your records. The values travel with each record as **extra** fields, which you can show in the [format](formatting.md#extra-fields) or get as typed fields in [JSON](json-output.md#json-with-context).

There are two tools:

* `bind()` creates a new logger that **always** adds some values.
* `contextualize()` adds values **temporarily**, inside a `with` block.

## Permanent context with `bind()` { #permanent-context-with-bind }

```python hl_lines="8-10"
--8<-- "docs_src/context/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

INFO | Opened the dashboard | {'session': 'a1b2', 'user_id': 42}
INFO | Changed the theme | {'session': 'a1b2', 'user_id': 42}
INFO | Background job finished | {}
```

</div>

`logger.bind(user_id=42, session="a1b2")` returns a **new** logger. Every record logged through `user_logger` carries those two values.

The original `logger` is not changed at all: `"Background job finished"` has no context. You can create as many bound loggers as you want, and they never interfere with each other.

/// tip

The format here uses `{extra}` to show all the context values. You saw it in [Formatting](formatting.md#all-values-with-extra). In real code you would usually use `{extra[user_id]}` for the values you care about, or [JSON output](json-output.md).

///

### Building on bound loggers { #building-on-bound-loggers }

A bound logger has `bind()` too, so you can add context step by step as you learn more:

```python hl_lines="8 11"
--8<-- "docs_src/context/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

INFO | Request received | {'request_id': 'r-17'}
INFO | User authenticated | {'request_id': 'r-17', 'user_id': 42}
INFO | Request finished | {'request_id': 'r-17'}
```

</div>

`user_logger` has both values. `request_logger` still has only `request_id`: binding never modifies the logger you call it on.

If you bind a key that is already bound, the new value wins for the new logger.

/// info

You can also add a value to a single record with a keyword argument: `logger.info("Invoice sent", invoice_id="INV-7")`. Keyword arguments that the message doesn't use go to `extra`, as you saw in [Message Arguments](message-arguments.md#extra-keyword-arguments-go-to-extra).

`bind()` is for values that belong to *many* records.

///

## Temporary context with `contextualize()` { #temporary-context-with-contextualize }

`bind()` has one limitation: you need to pass the bound logger around. Functions that use the global `logger` don't see its values.

`contextualize()` solves that. It adds values to the `logger` itself, for the duration of a `with` block:

```python hl_lines="14"
--8<-- "docs_src/context/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

INFO | Checkout started | {'order_id': 1234}
INFO | Charging 25 EUR | {'order_id': 1234}
INFO | Checkout done | {'order_id': 1234}
INFO | Waiting for the next order | {}
```

</div>

Look at `"Charging 25 EUR"`: `charge_card()` knows nothing about orders, it just uses the global `logger`. But because it runs inside the `with` block, its record has the `order_id` too. 🎉

When the block ends, even with an exception, the context is removed: `"Waiting for the next order"` is back to no context.

### Nested contexts { #nested-contexts }

Blocks can be nested. The inner block adds to the outer one, and leaving it restores the outer context:

```python hl_lines="8 11"
--8<-- "docs_src/context/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

INFO | User context | {'user_id': 42}
INFO | Both values | {'action': 'login', 'user_id': 42}
INFO | Only user_id again | {'user_id': 42}
```

</div>

If an inner block uses a key that the outer one already has, the inner value is used until the inner block ends.

### What `contextualize()` changes { #what-contextualize-changes }

`contextualize()` changes the logger object it is called on, until the block ends. That has a few consequences that are good to know:

* It applies to that logger object only. Loggers created with `bind()` **before** the block don't get the values, and a logger you `bind()` **inside** the block keeps them after the block ends (a bound logger is a snapshot of the context when it was created).
* The change is visible to **all threads and asyncio tasks** that use that logger while the block is running, not only to the code inside the block.

/// warning

Because of that second point, don't use `contextualize()` on a shared logger when several requests or tasks run at the same time (threads, `asyncio.gather()`, async web frameworks). Their values would mix: a record from one task could carry another task's `request_id`, and with overlapping blocks the context restored at the end may not be the original one.

For concurrent code, use `bind()` and pass the bound logger along, which is always safe. If you need context that follows the current request automatically, store it in a `contextvars.ContextVar` and add it to every record with a patcher, see [Records and patch()](../advanced/records-and-patch.md).

///

## Use cases { #use-cases }

### Web request logging { #web-request-logging }

A classic: give every request an ID, and bind it with the method and path. Then you can find all the lines of one request with a single search.

```python hl_lines="18-22"
--8<-- "docs_src/context/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

{"time":"2026-10-06 12:01:27.935","level":"INFO","message":"Request started","name":"__main__","function":"handle_request","line":23,"extra":{"request_id":"080787ae","method":"GET","path":"/orders"}}
{"time":"2026-10-06 12:01:27.935","level":"INFO","message":"Request completed","name":"__main__","function":"handle_request","line":25,"extra":{"request_id":"080787ae","method":"GET","path":"/orders"}}
```

</div>

This one uses [JSON output](json-output.md), where context really pays off: in your aggregator, `extra.request_id = "080787ae"` gives you the whole story of that request.

Because it uses `bind()`, it is safe even when many requests are handled at the same time.

### User session logging { #user-session-logging }

In a script, a CLI or a worker that handles one thing at a time, `contextualize()` lets every function deep in the call stack log with the user's details, without passing anything around:

```python hl_lines="20"
--8<-- "docs_src/context/tutorial006.py"
```

<div class="termy">

```console
$ python main.py

INFO | Processing action | user=42 action=update-settings
INFO | Settings saved | user=42 action=update-settings
```

</div>

`save_settings()` doesn't take a user, but its record says which user it was for.

## Beyond `bind()` and `contextualize()` { #beyond-bind-and-contextualize }

Sometimes you want to compute context **for each record**, for example to add the current request ID from a `ContextVar`, or to redact a secret. That is what `logger.patch()` is for, and it receives the full record dict. You will see both in [Records and patch()](../advanced/records-and-patch.md).

## Recap { #recap }

* Context values travel with each record as `extra`, shown with `{extra[key]}` / `{extra}` or as typed JSON fields.
* `logger.bind(key=value)` returns a new logger that always adds the values. The original logger is unchanged.
* Bound loggers can be bound again, to add context step by step.
* `with logger.contextualize(key=value):` adds values to `logger` itself until the block ends, so functions you call get them too. Blocks can be nested.
* `contextualize()` is visible to every thread and task using that logger: for concurrent code, use `bind()` instead.

Next, let's see what to do when things go wrong: [Logging Exceptions](exceptions.md).
