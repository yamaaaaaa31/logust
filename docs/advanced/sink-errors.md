# Sink Errors { #sink-errors }

Sinks can fail. A log service is down, a disk is full, a file can't be opened, a callable sink has a bug...

What should happen then? Should the error be ignored, reported, or should it crash the logging call? The answer depends on your app, so Logust lets you choose per handler, with the `catch=` option of `logger.add()`.

## The default: drop the error { #the-default-drop-the-error }

Here's a callable sink that always fails, next to a working console sink:

```python hl_lines="6-7 12"
--8<-- "docs_src/advanced_sink_errors/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

INFO | Order 42 shipped
```

</div>

The console sink works, and the error of `send_to_service()` is **silently dropped**. Your app keeps running, but you don't know that half of your logs are missing. 😱

That's the default, `catch=None`. It keeps existing apps from suddenly writing reports to stderr, but in most apps you'll want to know when a sink fails.

## Report the error: catch=True { #report-the-error-catch-true }

With `catch=True`, Logust prints a **report** to stderr, and logging continues:

```python hl_lines="12"
--8<-- "docs_src/advanced_sink_errors/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

--- Logging error in Logust Handler #2 ---
Record was: {'timestamp': '2026-10-06T12:07:03.434788+09:00', 'level': 'INFO', 'name': '__main__', 'function': '<module>', 'line': 14, 'message': 'Order 42 shipped'}
Traceback (most recent call last):
  File "/home/user/project/.venv/lib/python3.13/site-packages/logust/_logger.py", line 2328, in reporting_wrapper
    emit(record)
    ~~~~^^^^^^^^
  File "/home/user/project/.venv/lib/python3.13/site-packages/logust/_logger.py", line 2322, in emit
    sink(render(record))
    ~~~~^^^^^^^^^^^^^^^^
  File "/home/user/project/main.py", line 7, in send_to_service
    raise ConnectionError("log service unavailable")
ConnectionError: log service unavailable
--- End of logging error ---
INFO | Order 42 shipped
```

</div>

The report has everything you need to fix it:

* `Handler #2`: the ID of the failing handler, the one `logger.add()` returned.
* `Record was:`: the message that couldn't be written.
* The **traceback** of the error.

The message still reached the console sink, and the logging call didn't fail.

/// tip

`catch=True` is loguru's default. If you're used to loguru, or if you want to know when logs go missing, pass `catch=True` to your sinks. 🤓

///

## Raise the error: catch=False { #raise-the-error-catch-false }

Sometimes a failed log write is a **real problem**: an audit log, for example, where a missing entry is not acceptable. With `catch=False`, the error is raised from the logging call:

```python hl_lines="12 14-17"
--8<-- "docs_src/advanced_sink_errors/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

INFO | Order 42 shipped
The logging call raised: ConnectionError('log service unavailable')
```

</div>

Every other handler still receives the message first, and then the error is raised. If several sinks fail, the first error is raised.

## The three options { #the-three-options }

| `catch=` | When a sink fails |
|----------|-------------------|
| `None` (default) | The error is dropped silently. |
| `True` | A report goes to stderr, and logging continues. |
| `False` | The error is raised from the logging call (`OSError` for file sinks). |

`catch=` works for every kind of sink: a callable that raises, a stream whose `write()` raises, a file that can't be opened or written.

/// note | Difference from loguru

loguru's default is `catch=True`. Logust keeps `None` (silent) as the default, so existing applications don't start writing reports to stderr after an upgrade. Pass `catch=True` to match loguru.

///

## File sinks { #file-sinks }

For file sinks, there are a couple of details:

* `logger.add("app.log")` opens the file right away. If it **can't be opened** (a directory with that name, no permission...), `add()` raises an `OSError` immediately, whatever `catch=` is.
* With `delay=True`, the file is opened at the first message instead. So an error when opening it happens at that first write, and follows the `catch=` setting.
* With [`enqueue=True`](async-writes.md), the writes happen on a background thread. Write errors are printed to stderr there, whatever `catch=` is set to, because there's no logging call left to raise them from.

## Recap { #recap }

* `catch=` on `logger.add()` decides what happens when a sink fails.
* `None` (default) drops the error, `True` reports it to stderr, `False` raises it.
* The report starts with `--- Logging error in Logust Handler #<id> ---` and includes the record and the traceback.
* Use `catch=True` to know when logs go missing, and `catch=False` when a missing log is not acceptable.
