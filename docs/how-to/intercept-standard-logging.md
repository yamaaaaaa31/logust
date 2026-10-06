# Intercept Standard Logging { #intercept-standard-logging }

Your own code uses Logust, but the libraries you depend on (`urllib3`, `httpx`, `sqlalchemy`, `uvicorn`, ...) log with the standard `logging` module. By default, those messages go to `logging`'s own handlers, with a different format, and they skip your Logust files, rotation and JSON output.

This recipe routes **everything** logged with `logging` through Logust, so all your logs end up in the same place, with the same format. 🎉

## The one-liner { #the-one-liner }

Call `intercept_logging()` from `logust.contrib`:

```python hl_lines="3 5"
--8<-- "docs_src/how_to_intercept_standard_logging/tutorial001.py"
```

Every `logging` call, from your code or from any library, now goes to Logust:

<div class="termy">

```console
$ python main.py

2026-10-06 11:57:44.402 | INFO     | ::0 - Hello from the standard library
2026-10-06 11:57:44.402 | WARNING  | ::0 - Slow query: 1.73 s
```

</div>

The `%`-style arguments of `logging` (`"%.2f s", 1.73`) are applied by `logging` before the message reaches Logust, so they keep working as before.

/// warning | Empty caller fields

Look at the `::0` in the middle. The default format shows the caller as `{name}:{function}:{line}`, but records forwarded from `logging` don't carry those fields: they are empty, and the line is `0`.

If most of your logs come from `logging`, use a format without the caller fields, as in the next section.

///

## A format for intercepted records { #a-format-for-intercepted-records }

Replace the default handler with one whose format doesn't use `{name}`, `{function}` or `{line}`:

```python hl_lines="7-8"
--8<-- "docs_src/how_to_intercept_standard_logging/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 11:57:44.469 | WARNING  | Slow query: 1.73 s
```

</div>

You can read more about formats in [Formatting](../tutorial/formatting.md) and about replacing the default handler in [Handlers and Sinks](../tutorial/sinks.md#replace-the-default-handler).

## How it works { #how-it-works }

`intercept_logging()` does three things:

* It sets the handlers of the **root** `logging` logger to a single `InterceptHandler`.
* It sets the root level to `level` (`logging.DEBUG` by default, so every record is forwarded).
* It removes the handlers of every `logging` logger that **already exists** and makes them propagate to the root.

From then on, each `logging` record travels up to the root logger, and `InterceptHandler` hands it to Logust with:

* The **level name** of the record (`"INFO"`, `"WARNING"`, ...).
* The **message**, already formatted by `logging` (`record.getMessage()`).
* The **traceback**, when the record has `exc_info` (for example from `logging.exception()`).

After that, it is a normal Logust message: it goes to all your handlers, with their levels, formats, filters, rotation and JSON output.

/// tip

Call `intercept_logging()` **after** any code that configures `logging` itself, for example after `logging.basicConfig()` in a library or framework you use. It only resets the loggers that exist at the moment you call it.

///

The full signature is:

```python
intercept_logging(level: int = logging.DEBUG, target: Logger | None = None) -> None
```

* `level`: the minimum `logging` level forwarded. `logging` drops lower records before they reach Logust.
* `target`: the Logust logger that receives the records. `None` means the global `logger`. See [Tag intercepted records](#tag-intercepted-records).

## Manual setup with `InterceptHandler` { #manual-setup-with-intercepthandler }

If you want more control, install the handler yourself. `InterceptHandler` is a normal `logging.Handler`, so you can use it anywhere `logging` takes one:

```python hl_lines="3 5"
--8<-- "docs_src/how_to_intercept_standard_logging/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 11:57:44.535 | INFO     | ::0 - Routed by a handler you installed yourself
```

</div>

Here `logging` itself drops the `DEBUG` message, because of `level=logging.INFO`.

/// note

`force=True` makes `basicConfig()` replace any handlers the root logger already has. Without it, `basicConfig()` does nothing if the root logger is already configured.

///

You can also attach `InterceptHandler` to a single logger instead of the root:

```python
logging.getLogger("sqlalchemy.engine").addHandler(InterceptHandler())
```

## Silence a noisy library { #silence-a-noisy-library }

Intercepted records are matched against the **`logging` logger name** for `logger.disable()`. So you can turn off a library by its logger name:

```python hl_lines="8"
--8<-- "docs_src/how_to_intercept_standard_logging/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 11:57:44.598 | INFO     | ::0 - Your own logs still go through
```

</div>

`logger.disable("urllib3")` drops records from `urllib3` and every `urllib3.*` logger. You can learn more about these rules in [Logging in Libraries](../advanced/library-logging.md).

## Custom `logging` levels { #custom-logging-levels }

Some code defines its own `logging` levels, like `35`. Logust needs to know the level **by name** to forward the record.

/// danger

If a `logging` record has a level that Logust doesn't know, `InterceptHandler` raises `ValueError: Invalid log level`, and the exception propagates to the code that made the `logging` call.

This happens with:

* A number without a name: `log.log(35, "...")` gives the level name `"Level 35"`.
* A name registered only in `logging`: `logging.addLevelName(35, "NOTICE")`.

///

To make it safe, register the **same name** in both places, before the first message:

```python hl_lines="6-7"
--8<-- "docs_src/how_to_intercept_standard_logging/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 11:57:44.670 | NOTICE   | ::0 - Disk usage is at 91%
```

</div>

The built-in `logging` levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) always work. Read more about `logger.level()` in [Custom Levels](../advanced/custom-levels.md).

## Tag intercepted records { #tag-intercepted-records }

You can pass a **bound** logger as `target`. Its context is added to every intercepted record, so you can tell them apart from your own logs:

```python hl_lines="8"
--8<-- "docs_src/how_to_intercept_standard_logging/tutorial006.py"
```

The console looks as usual:

<div class="termy">

```console
$ python main.py

2026-10-06 11:57:44.733 | INFO     | ::0 - Tagged so you can tell it apart
2026-10-06 11:57:44.733 | INFO     | __main__:<module>:11 - Logged with logust directly
```

</div>

And `app.json` has the `source` field only on the intercepted record:

```json
{"time":"2026-10-06 11:57:44.733","level":"INFO","message":"Tagged so you can tell it apart","extra":{"source":"stdlib"}}
{"time":"2026-10-06 11:57:44.733","level":"INFO","message":"Logged with logust directly","name":"__main__","function":"<module>","line":11}
```

`InterceptHandler(target=...)` takes the same argument.

## Recap { #recap }

* `intercept_logging()` sends every `logging` record, from your code and from libraries, to Logust.
* Call it after other code has configured `logging`.
* For finer control, use `InterceptHandler` with `basicConfig()` or on a single logger.
* Intercepted records have no caller fields, so prefer a format without `{name}:{function}:{line}`.
* `logger.disable("libname")` silences a library by its `logging` logger name.
* Register custom `logging` levels in Logust with the same name, or they raise `ValueError`.
