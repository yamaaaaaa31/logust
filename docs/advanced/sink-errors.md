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

## Console sinks and broken pipes { #console-sinks-and-broken-pipes }

Console sinks (`sys.stdout`, `sys.stderr` and the default handler) follow the same `catch=` policy. Their usual failure is a reader that has gone away, as when you pipe your program into `head`:

```python hl_lines="6"
--8<-- "docs_src/advanced_sink_errors/tutorial004.py"
```

<div class="termy">

```console
$ python main.py | head -n 1

INFO | Processing item 0
Done: 1000 items processed
```

</div>

`head` reads the first line and exits. From then on, every write to stdout fails with a **broken pipe** (`EPIPE`), because Python ignores the `SIGPIPE` signal that would otherwise stop the program.

With the default `catch=None`, your program keeps running, and the console output that nobody reads anymore is dropped: `"Done"` (written to stderr, not to the pipe) shows that all 1,000 items were processed. 😎

The other values work as for any other sink:

| `catch=` | When the reader of a console sink has gone away |
|----------|-------------------------------------------------|
| `None` (default) | The program keeps running, and the console output is dropped. |
| `True` | A report is printed to stderr for **each** dropped message (nothing is printed if stderr itself is the broken pipe). |
| `False` | The logging call raises `BrokenPipeError`. |

With `catch=True`, each report looks like this:

```
--- Logging error in Logust Handler #1 ---
Record was: INFO | Processing item 157
OSError: Broken pipe (os error 32)
--- End of logging error ---
```

and with `catch=False`, the program stops at the first message that can't be written:

```
Traceback (most recent call last):
  File "/home/user/project/main.py", line 9, in <module>
    logger.info("Processing item {}", i)
    ...
BrokenPipeError: Broken pipe (os error 32)
```

/// note

A closed descriptor (for example after `os.close(1)`) is not a broken pipe: writes to it are still treated as successful, and nothing is reported or raised.

///

## Recap { #recap }

* `catch=` on `logger.add()` decides what happens when a sink fails.
* `None` (default) drops the error, `True` reports it to stderr, `False` raises it.
* The report starts with `--- Logging error in Logust Handler #<id> ---` and includes the record and the traceback.
* Use `catch=True` to know when logs go missing, and `catch=False` when a missing log is not acceptable.
* A console sink whose reader has gone away (`python main.py | head`) never crashes your program by default: the output is dropped. `catch=True` reports each dropped message, `catch=False` raises `BrokenPipeError`.
