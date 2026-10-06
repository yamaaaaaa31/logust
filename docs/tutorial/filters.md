# Filtering Records { #filtering-records }

You already know how to choose *which levels* a sink receives with `level=`. But sometimes the level is not enough:

* An `audit.log` file that only gets security-relevant events.
* A third-party library that is too chatty.
* `INFO` to stdout, but `WARNING` and above to stderr.

For all of these, each sink takes a **filter**: a function that looks at a record and decides whether that sink should write it.

## A first filter { #a-first-filter }

A filter is any callable that receives the record (a dict) and returns `True` to keep it, `False` to skip it. Pass it to `logger.add()` with `filter=`:

```python hl_lines="4-5 8"
--8<-- "docs_src/filters/tutorial001.py"
```

Run it, then look at the file:

<div class="termy">

```console
$ python main.py

2026-10-06 12:04:32.161 | INFO     | __main__:<module>:10 - Cache warmed up
2026-10-06 12:04:32.161 | INFO     | __main__:<module>:11 - Changed the billing address
2026-10-06 12:04:32.161 | WARNING  | __main__:<module>:12 - Deleted an invoice

$ cat audit.log

2026-10-06 12:04:32.161 | Changed the billing address | user=alice
2026-10-06 12:04:32.161 | Deleted an invoice | user=bob
```

</div>

The console (the default sink, with no filter) shows everything. `audit.log` only has the two records that were bound with `audit=True`. 🎉

The filter only applies to the sink it was given to. Every sink decides on its own.

/// tip

The `logger.complete()` at the end makes sure everything waiting to be written reaches the files before the program exits. It is a good habit at the end of a script that writes to files.

///

## The record dict { #the-record-dict }

The record your filter receives has the same shape as loguru's, so filters written for loguru usually work as is. These are the keys you will use the most:

| Key | Value |
|-----|-------|
| `record["level"]` | The level. Compare it as a string (`record["level"] == "INFO"`), or use `.name` and `.no` |
| `record["message"]` | The message, with its arguments applied |
| `record["name"]` | Module `__name__` of the caller, like `myapp.payments` |
| `record["function"]`, `record["line"]` | Caller function and line |
| `record["file"]` | Caller file name, with `.name` and `.path` |
| `record["extra"]` | The [context values](context.md) |
| `record["exception"]` | The traceback text, or `None` |
| `record["time"]` | The time of the record, an aware `datetime` |

You will find the complete list in [Records and patch()](../advanced/records-and-patch.md).

/// warning

In the record dict, the values in `record["extra"]` are **strings**: `bind(user_id=42)` gives `record["extra"]["user_id"] == "42"`.

So `bind(audit=False)` gives `"False"`, which is truthy! That's why the example above checks whether the key is **present** (`"audit" in record["extra"]`) instead of reading its value. Compare with strings, or convert, when you need the value.

///

## Filter by module { #filter-by-module }

`record["name"]` is the module that logged the record. That makes it easy to silence a noisy module.

Imagine a library `chatty_sdk` that logs a lot:

```python
--8<-- "docs_src/filters/chatty_sdk.py"
```

Keep everything except what comes from it:

```python hl_lines="8-9 13"
--8<-- "docs_src/filters/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

INFO     | __main__ | Fetching exchange rates
INFO     | __main__ | Got 2 rates
```

</div>

`startswith("chatty_sdk")` also matches its submodules, like `chatty_sdk.http`.

/// note

loguru also accepts a string (`filter="myapp"`) or a dict (`filter={"myapp": "INFO"}`) as a filter. In Logust, `filter=` must be a callable. A string or a dict is currently accepted without an error but has **no effect**: every record goes through. Use a function like the one above.

///

/// tip

If the module is a library that logs with Logust, you can also turn its logs off everywhere, for every sink, with `logger.disable("chatty_sdk")`. See [Logging in Libraries](../advanced/library-logging.md).

///

## A minimum level per module { #a-minimum-level-per-module }

Silencing the library completely hides its warnings too, and we probably want to know that we are about to hit a rate limit. 😅

Let's instead give each module its own minimum level, with a small dict and a filter that reads `record["level"].no`:

```python hl_lines="7-9 12-13 17"
--8<-- "docs_src/filters/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

DEBUG    | __main__ | Fetching exchange rates
WARNING  | chatty_sdk | Rate limit almost reached
INFO     | __main__ | Got 2 rates
```

</div>

Your own code logs from `DEBUG` up, and `chatty_sdk` only from `WARNING` (30) up. `.no` is the numeric severity of the level: `TRACE` is 5, `DEBUG` 10, `INFO` 20, `SUCCESS` 25, `WARNING` 30, `ERROR` 40, `FAIL` 45, `CRITICAL` 50.

## Combining a filter with `level` { #combining-a-filter-with-level }

`level=` gives a **minimum**. A filter can add a **maximum**. Together, they can split your logs between stdout and stderr, which is what many process managers expect:

```python hl_lines="8 10 12"
--8<-- "docs_src/filters/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

stdout | DEBUG    | Loading plugins
stdout | INFO     | Server ready
stderr | WARNING  | Slow response: 1200 ms
stderr | ERROR    | Database connection lost

// Only what goes to stdout
$ python main.py 2> /dev/null

stdout | DEBUG    | Loading plugins
stdout | INFO     | Server ready
```

</div>

* The stdout sink takes `DEBUG` and up (`level="DEBUG"`), but the filter drops `WARNING` and up (`record["level"].no < 30`).
* The stderr sink takes `WARNING` and up, with no filter.

Each record ends up in exactly one place.

/// tip | Performance

Logust checks `level=` **before** calling your filter. If a record is below a sink's level, the filter of that sink is not even called. So set `level=` as high as makes sense, and let the filter handle only what the level can't express. 🚀

///

/// note

If a filter raises an exception, Logust keeps the record (as if the filter had returned `True`) and doesn't report the error. Keep filters small and safe: use `record["extra"].get("key")` rather than `record["extra"]["key"]` when a key may be missing.

///

## Recap { #recap }

* `filter=` on `logger.add()` takes a callable that receives the record dict and returns `True` to keep it.
* Filters work per sink: each sink keeps its own.
* `record["name"]` filters by module, `record["level"].no` by severity, `record["extra"]` by context (its values are strings).
* String and dict filters (loguru style) don't work in Logust: write a function.
* `level=` is checked first and is cheaper. Use a filter for what the level can't express, like a maximum level.

## What's next { #whats-next }

That's the end of the **Tutorial - User Guide**. 🎉

You now know how to log at different levels, write to the console and to files, rotate them, choose a format or JSON, add context, log exceptions and filter records. That's everything most applications need.

From here, you can:

* Continue with the [Advanced User Guide](../advanced/index.md): custom levels, records and `patch()`, `opt()`, callbacks, tracebacks with variable values, asynchronous writes, performance tuning and more.
* Jump to the [How To - Recipes](../how-to/index.md) for ready-made solutions: using Logust with FastAPI, intercepting the standard `logging` module, migrating from loguru, and others.
