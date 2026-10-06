# Records and patch() { #records-and-patch }

Every time you call `logger.info()`, Logust builds a **record**: a dict with the message, the level, the time, where the call happened, the bound context, and more.

You already used records in [filters](../tutorial/filters.md). Here you'll see everything a record holds, and how to change records before they are written with `logger.patch()`.

## What's in a record { #whats-in-a-record }

The easiest way to see a record is to print one. A [callback](callbacks.md) receives every record as a dict, so let's use one:

```python hl_lines="6-8 11"
--8<-- "docs_src/advanced_records_and_patch/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

        user: 'alice'
    level_no: 20
     message: 'Order 42 placed'
   timestamp: '2026-10-06T12:02:31.834759+09:00'
        name: '__main__'
    function: 'checkout'
        line: 15
 thread_name: 'MainThread'
   thread_id: 8348778368
process_name: 'MainProcess'
  process_id: 49394
       level: 'INFO'
        file: 'main.py'
      module: 'main'
      thread: (id=8348778368, name='MainThread')
     process: (id=49394, name='MainProcess')
        time: datetime.datetime(2026, 10, 6, 12, 2, 31, 834759, tzinfo=datetime.timezone(datetime.timedelta(seconds=32400)))
     elapsed: RecordElapsed(0)
       extra: {'user': 'alice'}
   exception: None
```

</div>

That's a lot of information for one line of code. 😎

The record is **shaped like loguru's**, so filters written for loguru keep working. Here are the keys:

| Key | Value |
|-----|-------|
| `message` | The formatted message. |
| `level` | The level name. It's a `str`, so `record["level"] == "INFO"` works, and it also has loguru's `.name`, `.no` and `.icon`. |
| `time` | The time of the record, as an aware `datetime`. |
| `elapsed` | A `timedelta` since the logger started. `str()` gives `HH:MM:SS.mmm`. |
| `name` | The module `__name__` of the caller. |
| `module` | The caller's file name without the extension. |
| `function`, `line` | The caller's function and line number. |
| `file` | The caller's file name. A `str` with loguru's `.name` and `.path`. |
| `thread`, `process` | Objects with `.id` and `.name`. |
| `exception` | The formatted traceback text, or `None`. |
| `extra` | The bound context and extra keyword arguments. |

And Logust adds a few **flat keys** with the same information: `level_no`, `timestamp` (the time as an RFC 3339 string), `thread_name`, `thread_id`, `process_name` and `process_id`.

Bound values are also copied to the **top level** of the record, that's why `user` shows up first above. A bound value doesn't overwrite one of the keys in the table.

## Using the record's attributes { #using-the-records-attributes }

Several values are more than plain strings. Let's keep the records a callback receives, and look at the last one:

```python hl_lines="14-23"
--8<-- "docs_src/advanced_records_and_patch/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

level:   WARNING (no=30, icon=⚠️)
is warn: True
file:    main.py
thread:  MainThread
process: MainProcess
time:    2026-10-06T12:02:49.519198+09:00
hour:    12
elapsed: 00:00:00.255
```

</div>

So, in a filter, you can write things like:

```python
logger.add("warnings.log", filter=lambda r: r["level"].no >= 30)
logger.add("app.log", filter=lambda r: r["file"].name != "noisy.py")
logger.add("night.log", filter=lambda r: r["time"].hour < 6)
```

/// note | Technical Details

`elapsed` counts from the moment the logger started, which in practice is the **first** message your program logs. That's why the second message above shows `00:00:00.255`: it came 250 ms after the first one.

///

### Differences from loguru { #differences-from-loguru }

Most loguru code just works, but there are a few differences to keep in mind:

* `record["exception"]` is the **traceback text**, not loguru's `(type, value, traceback)` tuple. Test it with `record["exception"] is not None`, or search the text.
* In filters and callbacks, the values in `record["extra"]` are given **as text**: `logger.bind(count=5)` shows up as `record["extra"]["count"] == "5"`. The top-level copy (`record["count"]`) keeps the original value.
* `time`, `elapsed`, `thread` and `process` are not JSON-serializable. A callback that passes the whole record to `json.dumps()` should pick the keys it needs, or use `default=str`.
* The `level`, `file`, `thread` and `process` values are shared between records, so their attributes are read-only.

## Changing records with patch() { #changing-records-with-patch }

Sometimes you want to **add** or **change** something in every record, computed at the moment of the log call. That's what `logger.patch()` is for.

A **patcher** is a function that receives the record and modifies it in place. `logger.patch(patcher)` returns a new logger that runs it on every record:

```python hl_lines="12-13 16"
--8<-- "docs_src/advanced_records_and_patch/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

#1 | INFO    | Starting the import
#2 | INFO    | Imported 1200 rows
#3 | WARNING | Skipped 3 invalid rows
```

</div>

Each record gets the next number of the counter in `record["extra"]["seq"]`, and the format shows it with `{extra[seq]}`.

Notice that `logger.patch()` doesn't change `logger` itself. Like [`bind()`](../tutorial/context.md), it returns a **new** logger, and only messages logged through it are patched.

/// tip

`bind()` is for values you know when you create the logger. `patch()` is for values that must be computed **for each message**: a counter, the current request from a context variable, the memory usage...

///

## Chaining patchers { #chaining-patchers }

You can call `.patch()` on a patched logger. The patchers **accumulate**, and run in the order you added them.

A patcher can also change the message. Let's use that to hide a secret token, wherever it appears:

```python hl_lines="18-19 22"
--8<-- "docs_src/advanced_records_and_patch/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

#1 | INFO    | Calling the payments API with token ***
#2 | INFO    | Payment accepted
```

</div>

The token never reaches a sink. 🔒

### What a patcher can change { #what-a-patcher-can-change }

A patcher sees a record with the same keys as above, with a few differences:

* Only changes to `record["message"]`, `record["extra"]` and `record["exception"]` are used. Changes to other keys, like `record["level"]`, are ignored.
* The **caller fields** (`name`, `module`, `function`, `line`, `file`) are not there yet. They are collected after the patchers run.
* `time`, `timestamp`, `elapsed`, `thread` and `process` are computed the first time the patcher reads them. So a patcher that only touches `record["extra"]` doesn't pay for them.
* The values in `record["extra"]` keep their original Python types.

/// info

Patchers run before the filters, so a [filter](../tutorial/filters.md) can use a value that a patcher added to `extra`.

///

## A patcher for every message { #a-patcher-for-every-message }

To patch every message of the global `logger`, and of every logger made from it with `bind()` or `patch()`, pass the patcher to `logger.configure()`:

```python
logger.configure(patcher=add_sequence)
```

## Recap { #recap }

* Filters, patchers and callbacks receive a **record** dict shaped like loguru's.
* `record["level"].no`, `record["time"]`, `record["file"].name`, `record["thread"].name`... give you rich values to work with.
* `record["exception"]` is the traceback text, and in filters and callbacks `extra` values are text.
* `logger.patch(fn)` returns a logger that runs `fn` on every record before it's written.
* Patchers can change `message`, `extra` and `exception`, and they chain in order.
* `logger.configure(patcher=fn)` patches everything.
