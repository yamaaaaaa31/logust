# Callbacks { #callbacks }

A [sink](../tutorial/sinks.md) receives the **formatted text** of each message. That's what you want to write a line somewhere.

But sometimes you want to **react** to a message instead: send an alert when something fails, count errors, forward the data to a monitoring service. For that, the text is not very handy. You'd want the level, the context, the exception, as data.

That's what **callbacks** are for: a callback is a function that receives the full [record](records-and-patch.md) dict of every message.

## Add a callback { #add-a-callback }

Register a function with `logger.add_callback()`. You can give it a minimum `level`, like a handler:

```python hl_lines="9-10 13 23"
--8<-- "docs_src/advanced_callbacks/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

INFO    | Syncing inventory
  -> callback got WARNING from sync_inventory()
WARNING | Supplier API is slow
WARNING | Supplier API is still slow
```

</div>

Here's what happens:

* `add_callback(on_record, level="WARNING")` registers `on_record` for `WARNING` and above, and returns an **ID**.
* The `INFO` message doesn't reach the callback, the `WARNING` one does.
* The callback gets the record dict, so it can read `record["level"]`, `record["function"]`, and every other key.
* `remove_callback(callback_id)` unregisters it, so the last warning is only written by the handler.

Without `level`, a callback receives every message.

The callback runs **synchronously**, in the thread that logged the message, so keep it fast. If it has slow work to do (network calls...), hand it over to a queue or a background thread.

/// note

Use `logger.remove_callback(callback_id)` to remove a callback. `logger.remove(callback_id)` doesn't remove it. `logger.remove()` without an ID removes everything, callbacks included.

`remove_callback()` returns `True` if the callback was removed, and `False` if there was nothing to remove.

///

## Error monitoring { #error-monitoring }

The classic use case: send every error to your error tracker, with all the context you have.

```python hl_lines="16-21 24"
--8<-- "docs_src/advanced_callbacks/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

INFO     | Charging 19.99 EUR
  [ALERT] Payment failed
          where: __main__:charge:33
          order_id: ord_42
          error: ConnectionError: payment provider timed out
ERROR    | Payment failed
Traceback (most recent call last):
  File "/home/user/project/main.py", line 31, in charge
    raise ConnectionError("payment provider timed out")
ConnectionError: payment provider timed out
```

</div>

The callback builds the alert from the record:

* **Where** it happened: `record["name"]`, `record["function"]` and `record["line"]`.
* The **context**: `record["extra"]` has the `order_id` bound with [`bind()`](../tutorial/context.md).
* The **error**: `record["exception"]` is the traceback text (or `None`), so the last line is the exception type and message.

In a real app, `send_alert()` would call something like `sentry_sdk.capture_message()` or post to a webhook.

/// tip

Bind IDs (user, order, request...) with `bind()` or [`contextualize()`](../tutorial/context.md) in your code, and your error callback gets them for free. An alert that says *which* order failed is much more useful. 😎

///

## Callbacks vs callable sinks { #callbacks-vs-callable-sinks }

Both call your function for each message. The difference is what they pass to it:

| | Callable sink: `logger.add(fn)` | Callback: `logger.add_callback(fn)` |
|-|---------------------------------|-------------------------------------|
| Receives | The formatted text (a `str`) | The record (a `dict`) |
| Options | `format`, `filter`, `serialize`, `colorize`, `catch`... | `level` |
| Removed with | `logger.remove(id)` | `logger.remove_callback(id)` |
| Good for | Writing lines somewhere | Reacting to messages |

If you need JSON text, a callable sink with `serialize=True` gives you that directly. If you need the values, use a callback.

## Errors in a callback { #errors-in-a-callback }

If your callback raises an exception, the exception is ignored: the message is still written by the other handlers, and the logging call doesn't fail.

That keeps a broken alert integration from taking down your app, but it also hides the problem. If you want to know when your callback fails, catch errors inside it and report them yourself.

## Recap { #recap }

* `logger.add_callback(fn, level=...)` calls `fn` with the record dict of each message.
* `logger.remove_callback(callback_id)` removes it.
* Callbacks are perfect for error monitoring: the record has the level, the caller, the bound context and the traceback.
* Use a callable sink for formatted text, and a callback for data.
