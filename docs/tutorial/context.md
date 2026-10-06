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

`contextualize()` solves that. It adds values to everything logged inside a `with` block:

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

### Every logger sees it { #what-contextualize-changes }

The values of a `contextualize()` block are not attached to one logger object. They belong to the code running inside the block, so **every** logger sees them there: `logger` itself, loggers created with `bind()` (before or inside the block), and the module-level functions like `logust.info()`.

```python hl_lines="8 11 12"
--8<-- "docs_src/context/tutorial009.py"
```

<div class="termy">

```console
$ python main.py

INFO | Query sent | {'component': 'db', 'request_id': 'r-17'}
INFO | Retrying | {'attempt': 2, 'request_id': 'r-17'}
INFO | Retry finished | {'attempt': 2}
```

</div>

`db_logger` was created **before** the block, and it still gets the `request_id` inside it.

`retry_logger` was created **inside** the block, but it doesn't keep the `request_id` after the block ends: it only keeps what you passed to `bind()` itself. A bound logger never takes a snapshot of the `contextualize()` values, it reads them each time it logs.

/// tip

The block yields the logger it was opened on, so you can also write `with logger.contextualize(order_id=1234) as log:` and use `log` inside.

///

### Context-local: safe with threads and `asyncio` { #context-local }

Here is the best part. The values live in a [`contextvars`](https://docs.python.org/3/library/contextvars.html) variable, the same mechanism loguru uses. That makes them **context-local**: each thread and each asyncio task sees only the blocks it entered itself.

So you can use `contextualize()` in concurrent code, like several requests handled at the same time:

```python hl_lines="16 23"
--8<-- "docs_src/context/tutorial007.py"
```

<div class="termy">

```console
$ python main.py

INFO | Checkout started | {'order_id': 1}
INFO | Checkout started | {'order_id': 2}
INFO | Charging 25 EUR | {'order_id': 1}
INFO | Checkout done | {'order_id': 1}
INFO | Charging 40 EUR | {'order_id': 2}
INFO | Checkout done | {'order_id': 2}
INFO | All orders handled | {}
```

</div>

The two `handle_order()` tasks run at the same time, and their lines are interleaved. But each line has the `order_id` of its **own** task, even across the `await`. And `"All orders handled"`, logged by `main()` outside of both blocks, has no context at all. 🎉

That's exactly what you need in an async web framework: open a block with the request ID at the start of each request, and every line logged while handling that request carries it, without mixing it up with the other requests.

/// info

A task started **inside** a block inherits its values, because asyncio copies the current context when it creates a task. A new `threading.Thread` doesn't, by default. You will see the details, and how to pass the values to a thread, in [Threads and Processes](../advanced/threads-and-processes.md#context-in-threads-and-tasks).

///

### Precedence { #precedence }

The same key can come from several places. They are merged into `extra` in the same order as loguru, and **later sources win**:

1. `contextualize()` values of the current thread or task.
2. `bind()` values of the logger (and `configure(extra=...)`).
3. The message's own keyword arguments.

```python hl_lines="8 10 11"
--8<-- "docs_src/context/tutorial008.py"
```

<div class="termy">

```console
$ python main.py

INFO | Only contextualize() | {'step': 'checkout', 'user': 'from-contextualize'}
INFO | bind() wins | {'step': 'checkout', 'user': 'from-bind'}
INFO | The keyword argument wins | {'step': 'checkout', 'user': 'from-kwarg'}
```

</div>

Only `user` is overridden. `step` comes from the block in all three records, because nothing else sets it.

The more specific the source, the higher it wins: a block applies to everything in it, a bound logger to its own records, and a keyword argument to one single record.

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

Here `bind()` is a good fit, because `handle_request()` logs through `req_logger` directly. If the request also calls functions that use the global `logger`, open a `contextualize()` block instead (or as well), as in [Context-local: safe with threads and `asyncio`](#context-local).

### User session logging { #user-session-logging }

`contextualize()` lets every function deep in the call stack log with the user's details, without passing anything around:

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
* `with logger.contextualize(key=value):` adds values to every record logged inside the block, by any logger, so functions you call get them too. Blocks can be nested.
* `contextualize()` is context-local: each thread and asyncio task sees only its own blocks, so it is safe for concurrent requests.
* When a key comes from several places, `contextualize()` < `bind()` < the message's keyword arguments.

Next, let's see what to do when things go wrong: [Logging Exceptions](exceptions.md).
