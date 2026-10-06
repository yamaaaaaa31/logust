# Function Timing Decorators { #function-timing-decorators }

Sometimes you just want to know **how long a function takes**, without adding `time.perf_counter()` calls and a log line to each one.

`logust.contrib` has two decorators for that: `@log_fn` and `@debug_fn`. Put one on a function, and every call logs the function name and its elapsed time. ⏱

## Time a function with `@log_fn` { #time-a-function-with-log-fn }

```python hl_lines="3 6"
--8<-- "docs_src/how_to_timing_decorators/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:00:06.889 | INFO     | __main__:<module>:12 - Called process_data with elapsed_time=0.122
[2, 4, 6]
```

</div>

The function works exactly as before: it gets the same arguments and returns the same value. After it returns, `@log_fn` logs:

* At the `INFO` level.
* The message `Called <function name> with elapsed_time=<seconds>`, with the seconds rounded to 3 decimals.

Notice the caller in the log: `__main__:<module>:12`. It's the line that **called** `process_data()`, not a line inside the decorator. That's usually what you want to see.

/// info

The elapsed time is only in the message text. It is not added as an extra field.

///

## Async functions { #async-functions }

Both decorators detect `async def` functions and time the whole `await`. Here with `@debug_fn`, which logs at the `DEBUG` level:

```python hl_lines="3 6"
--8<-- "docs_src/how_to_timing_decorators/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:00:07.042 | DEBUG    | __main__:main:13 - Called fetch_user with elapsed_time=0.050
{'id': 123, 'name': 'Alice'}
```

</div>

## Detailed timings with `@debug_fn` { #detailed-timings-with-debug-fn }

Use `@debug_fn` for small, frequent functions. Their timings are useful when you investigate a problem, but noise the rest of the time.

They only show up when the `DEBUG` level is enabled. Here the console level is set to `INFO`, so only the outer function is logged:

```python hl_lines="5 10 15"
--8<-- "docs_src/how_to_timing_decorators/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:00:07.116 | INFO     | __main__:<module>:16 - Called import_file with elapsed_time=0.000
```

</div>

/// tip

The default console level of Logust is `DEBUG`, so `@debug_fn` timings **are** shown until you raise the level. Read more in [Log Levels](../tutorial/log-levels.md#set-the-minimum-level).

///

## Choose the level { #choose-the-level }

`@log_fn` also accepts a `level`. Use it with parentheses, `@log_fn(level=...)`:

```python hl_lines="6 9 14"
--8<-- "docs_src/how_to_timing_decorators/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:00:07.382 | WARNING  | __main__:<module>:19 - Called slow_operation with elapsed_time=0.202
2026-10-06 12:00:07.383 | TIMING   | __main__:<module>:20 - Called quick_operation with elapsed_time=0.000
```

</div>

The level can be any built-in level name, or a [custom level](../advanced/custom-levels.md) you registered, like `TIMING` here. A dedicated level is handy: you can then send timings to their own file, or filter them out, by level.

`@debug_fn` is the same as `@log_fn(level="DEBUG")`, and doesn't take a `level`.

## When the function raises { #when-the-function-raises }

The time is logged **after** the function returns. If it raises an exception, nothing is logged and the exception propagates as usual:

```python
--8<-- "docs_src/how_to_timing_decorators/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:00:07.450 | INFO     | __main__:<module>:9 - Called divide with elapsed_time=0.000
divide() raised, and no timing line was logged
```

</div>

If you also want the error in your logs, combine it with [`@logger.catch`](../tutorial/exceptions.md#the-catch-decorator).

## Recap { #recap }

* `@log_fn` logs `Called <name> with elapsed_time=<seconds>` at `INFO` after each call.
* `@debug_fn` does the same at `DEBUG`.
* `@log_fn(level="...")` uses any level, including custom ones.
* Both work with sync and `async def` functions, and report the caller's location.
* Nothing is logged when the function raises.
