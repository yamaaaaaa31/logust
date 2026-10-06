# Filtering Records { #filtering-records }

You already know how to choose *which levels* a sink receives with `level=`. But sometimes the level is not enough:

* An `audit.log` file that only gets security-relevant events.
* A third-party library that is too chatty.
* `INFO` to stdout, but `WARNING` and above to stderr.

For all of these, each sink takes a **filter**: a function that looks at a record and decides whether that sink should write it. For the most common case, filtering by module, a filter can also be a plain **string** or **dict**, as in loguru.

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

`record["name"]` is the module that logged the record. Filtering by module is so common that `filter=` takes a **string** or a **dict** for it, without writing a function.

Imagine a library `chatty_sdk` that logs a lot:

```python
--8<-- "docs_src/filters/chatty_sdk.py"
```

### Only one module: a string { #only-one-module-a-string }

A string keeps only the records of that module **and its submodules**. Let's send everything the SDK says, `DEBUG` included, to its own file, while the console stays at `INFO`:

```python hl_lines="9"
--8<-- "docs_src/filters/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

INFO     | __main__ | Fetching exchange rates
WARNING  | chatty_sdk | Rate limit almost reached
INFO     | __main__ | Got 2 rates

$ cat sdk.log

DEBUG    | Opening connection to rates.example.com
DEBUG    | Received 512 bytes
WARNING  | Rate limit almost reached
```

</div>

`filter="chatty_sdk"` matches `chatty_sdk` and its submodules, like `chatty_sdk.http`, but not a module called `chatty_sdk_extra`: the match follows the dots. `filter=""` matches every module.

### Everything except a module: a dict { #everything-except-a-module-a-dict }

To keep everything **except** what comes from the SDK, map it to `False` in a dict:

```python hl_lines="8"
--8<-- "docs_src/filters/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

INFO     | __main__ | Fetching exchange rates
INFO     | __main__ | Got 2 rates
```

</div>

`False` drops every record from `chatty_sdk` and its submodules. The modules that are not in the dict are not affected.

/// tip

If the module is a library that logs with Logust, you can also turn its logs off everywhere, for every sink, with `logger.disable("chatty_sdk")`. See [Logging in Libraries](../advanced/library-logging.md).

///

## A minimum level per module { #a-minimum-level-per-module }

Silencing the library completely hides its warnings too, and we probably want to know that we are about to hit a rate limit. 😅

Let's instead give each module its own **minimum level**: that's what the values of the dict are for.

```python hl_lines="12"
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

Your own code logs from `DEBUG` up, and `chatty_sdk` only from `WARNING` up.

Here is how the dict works:

* Each record looks for **its module, then its parent modules** in the dict, and the first match decides. With `{"app": "INFO", "app.db": "ERROR"}`, a record from `app.db.pool` uses `"ERROR"`, and one from `app.api` uses `"INFO"`.
* The key `""` is the parent of every module: it's the **default** for the modules that aren't in the dict.
* A record whose module matches no key at all is kept.
* The values can be a level name (`"WARNING"`, or the name of a [custom level](../advanced/custom-levels.md)), a level number (`30`), `True` (keep everything from that module) or `False` (drop everything).

The dict doesn't replace `level=`: a record must pass the sink's `level=` **and** the filter.

/// tip | Performance

String and dict filters are checked in Rust, without calling into Python and without building the record dict. A string or dict filter is several times cheaper than a function doing the same thing, so prefer them when they can express what you need. 🚀

They still need the module name, so a sink with a string or dict filter makes Logust look up the caller, like `{name}` in a format does (see [Performance](../advanced/performance.md)).

///

/// note

Level names in the dict are looked up when you call `logger.add()`. A name that doesn't exist (yet) raises a `ValueError` right there, and so do negative numbers. A value of another type, or a key that is not a string, raises a `TypeError`. Register custom levels before using them in a filter.

///

If you need something a string or a dict can't express, write a function. The dict example above, as a function, looks like this:

```python
min_levels = {"chatty_sdk": 30}  # WARNING and above


def by_module(record):
    return record["level"].no >= min_levels.get(record["name"], 0)
```

`.no` is the numeric severity of the level: `TRACE` is 5, `DEBUG` 10, `INFO` 20, `SUCCESS` 25, `WARNING` 30, `ERROR` 40, `FAIL` 45, `CRITICAL` 50.

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

## When a filter raises { #when-a-filter-raises }

A filter is your code, and it can have a bug. Here, the filter reads `record["extra"]["role"]`, but not every record is bound with a `role`:

```python hl_lines="7 11"
--8<-- "docs_src/filters/tutorial006.py"
```

<div class="termy">

```console
$ python main.py

INFO     | Rotated the API keys
--- Logging error in Logust Handler #1 ---
Record was: INFO | Health check OK
Traceback (most recent call last):
  File "/home/user/project/main.py", line 7, in only_admins
    return record["extra"]["role"] == "admin"
           ~~~~~~~~~~~~~~~^^^^^^^^
KeyError: 'role'
--- End of logging error ---
```

</div>

When a filter raises, the record is **not written** to that sink, as in loguru, and the error follows the sink's `catch=` option, like a [sink error](../advanced/sink-errors.md):

| `catch=` | When the filter raises |
|----------|------------------------|
| `None` (default) | The record is dropped silently. |
| `True` | The record is dropped, and a report with the traceback goes to stderr (above). |
| `False` | The record is dropped, and the error is raised from the logging call, after the other sinks got the record. |

The other sinks are not affected: each sink runs its own filter.

To fix this filter, use `record["extra"].get("role")`, which gives `None` instead of raising when the key is missing. 🤓

## Recap { #recap }

* `filter=` on `logger.add()` takes a callable that receives the record dict and returns `True` to keep it.
* Filters work per sink: each sink keeps its own.
* `filter="mypkg"` keeps only `mypkg` and its submodules.
* `filter={"": "WARNING", "mypkg": "DEBUG", "noisy": False}` sets a minimum level per module, with `""` as the default. String and dict filters are checked in Rust, so they are cheap.
* In a function, `record["name"]` filters by module, `record["level"].no` by severity, `record["extra"]` by context (its values are strings).
* A filter that raises drops the record, and `catch=` decides whether the error is ignored, reported or raised.
* `level=` is checked first and is cheaper. Use a filter for what the level can't express, like a maximum level.

## What's next { #whats-next }

That's the end of the **Tutorial - User Guide**. 🎉

You now know how to log at different levels, write to the console and to files, rotate them, choose a format or JSON, add context, log exceptions and filter records. That's everything most applications need.

From here, you can:

* Continue with the [Advanced User Guide](../advanced/index.md): custom levels, records and `patch()`, `opt()`, callbacks, tracebacks with variable values, asynchronous writes, performance tuning and more.
* Jump to the [How To - Recipes](../how-to/index.md) for ready-made solutions: using Logust with FastAPI, intercepting the standard `logging` module, migrating from loguru, and others.
