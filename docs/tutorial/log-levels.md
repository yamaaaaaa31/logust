# Log Levels { #log-levels }

Not all messages are equally important. "Entering function `parse_config()`" is useful while you debug, "Out of disk space" is something you want to see at 3 AM. 🚨

Every message has a **level** that says how severe it is. Logust has one method per level:

```python
--8<-- "docs_src/log_levels/tutorial001.py"
```

Run it:

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:06.894</font> | <font color="#3465A4"><b>DEBUG   </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">4</font> - Config file has 12 keys
<font color="#8A8A8A">2026-10-06 12:01:06.894</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">5</font> - Server starting
<font color="#8A8A8A">2026-10-06 12:01:06.894</font> | <font color="#8AE234"><b>SUCCESS </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">6</font> - Database connected
<font color="#8A8A8A">2026-10-06 12:01:06.894</font> | <font color="#C4A000"><b>WARNING </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">7</font> - Cache is almost full
<font color="#8A8A8A">2026-10-06 12:01:06.894</font> | <font color="#CC0000"><b>ERROR   </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">8</font> - Could not send the email
<font color="#8A8A8A">2026-10-06 12:01:06.894</font> | <font color="#75507B"><b>FAIL    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">9</font> - Health check failed
<font color="#8A8A8A">2026-10-06 12:01:06.894</font> | <font color="#EF2929"><b>CRITICAL</b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">10</font> - Out of disk space
```

</div>

Seven lines for eight calls. Where is the `TRACE` message?

The [default handler](first-steps.md#the-default-handler) only shows messages from `DEBUG` up, so `trace()` was filtered out. That's what levels are for: you decide the **minimum level**, and everything below it is dropped.

## Built-in levels { #built-in-levels }

These are the levels Logust comes with, from the least to the most severe:

| Level | Method | Value | Color | Use it for |
|-------|--------|-------|-------|------------|
| `TRACE` | `logger.trace()` | 5 | Cyan | Very detailed tracing, like entering and leaving functions |
| `DEBUG` | `logger.debug()` | 10 | Blue | Information useful while debugging |
| `INFO` | `logger.info()` | 20 | Green | Normal events: startup, requests, jobs |
| `SUCCESS` | `logger.success()` | 25 | Bright green | Something worked as expected |
| `WARNING` | `logger.warning()` | 30 | Yellow | Something unexpected, but the program keeps going |
| `ERROR` | `logger.error()` | 40 | Red | An operation failed |
| `FAIL` | `logger.fail()` | 45 | Magenta | A check or a task failed |
| `CRITICAL` | `logger.critical()` | 50 | Bright red | The program may not be able to continue |

The **value** is what Logust compares: a message is shown when its value is greater than or equal to the minimum level of a handler.

/// info

`SUCCESS` comes from loguru. `FAIL` is specific to Logust: it sits between `ERROR` and `CRITICAL`.

///

/// tip

Need a level that is not in this list, like `NOTICE` or `AUDIT`? You can create your own, see [Custom Levels](../advanced/custom-levels.md).

///

## Set the minimum level { #set-the-minimum-level }

Let's say you only want warnings and errors on the console. Use `set_level()`:

```python hl_lines="3"
--8<-- "docs_src/log_levels/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:06.950</font> | <font color="#C4A000"><b>WARNING </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">7</font> - Cache is almost full
<font color="#8A8A8A">2026-10-06 12:01:06.950</font> | <font color="#CC0000"><b>ERROR   </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">8</font> - Could not send the email
```

</div>

The `DEBUG` and `INFO` messages are gone.

Level names are **case-insensitive**, so `"WARNING"`, `"warning"` and `"Warning"` all work.

### Use `LogLevel` { #use-loglevel }

If you prefer something your editor can autocomplete (and that a typo can't break), use the `LogLevel` enum instead of a string:

```python hl_lines="1 3"
--8<-- "docs_src/log_levels/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:07.008</font> | <font color="#C4A000"><b>WARNING </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">6</font> - Cache is almost full
```

</div>

`LogLevel` has one member per built-in level: `LogLevel.Trace`, `LogLevel.Debug`, `LogLevel.Info`, `LogLevel.Success`, `LogLevel.Warning`, `LogLevel.Error`, `LogLevel.Fail` and `LogLevel.Critical`.

/// note | Technical Details

`set_level()` changes the minimum level of the **console** handlers: the default handler, and any handler you add for `sys.stdout` or `sys.stderr`.

Handlers that write to files or to Python functions keep the level you gave them when you added them. You will see how to choose that per-handler level in [Handlers and Sinks](sinks.md#a-level-per-handler).

///

## Check the current level { #check-the-current-level }

`get_level()` returns the current console level as a `LogLevel`, with a `name` and a numeric `value`.

`is_level_enabled()` tells you if a message at a given level would be logged by **at least one** handler:

```python hl_lines="5-6 8-9"
--8<-- "docs_src/log_levels/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

Current level: INFO (20)
DEBUG enabled? False
INFO enabled? True
```

</div>

### Skip expensive work { #skip-expensive-work }

`is_level_enabled()` is most useful to avoid work that only matters for a message nobody will see:

```python hl_lines="11-12"
--8<-- "docs_src/log_levels/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:07.126</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">14</font> - Done
```

</div>

With the level at `INFO`, `build_report()` is never called. Turn the level down to `DEBUG` and the report shows up.

/// tip

For a one-off value there is a shorter way: `logger.opt(lazy=True)`, which only calls your functions when the message is going to be logged. See [`opt()`](../advanced/opt.md) in the Advanced User Guide.

///

## Log with a level name { #log-with-a-level-name }

Sometimes the level is only known at runtime, for example, it comes from a config file. For that, use `logger.log()` with the level name or its number:

```python hl_lines="3-5"
--8<-- "docs_src/log_levels/tutorial007.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:07.251</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">3</font> - Logged with a level name
<font color="#8A8A8A">2026-10-06 12:01:07.251</font> | <font color="#C4A000"><b>WARNING </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">4</font> - Level names are case-insensitive
<font color="#8A8A8A">2026-10-06 12:01:07.251</font> | <font color="#CC0000"><b>ERROR   </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">5</font> - Logged with a level number
```

</div>

`logger.log()` is also how you log at a [custom level](../advanced/custom-levels.md).

## Turn the console off and on { #turn-the-console-off-and-on }

You can switch the console output off completely with `disable()`, and bring it back with `enable()`:

```python hl_lines="5 9"
--8<-- "docs_src/log_levels/tutorial006.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:07.187</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">3</font> - Before disable()
Console enabled? False
<font color="#8A8A8A">2026-10-06 12:01:07.187</font> | <font color="#C4A000"><b>WARNING </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">11</font> - Console is back
```

</div>

Here's what happened:

* `logger.disable()` removed the console handler, so `"Nobody sees this"` went nowhere.
* `logger.is_enabled()` tells you if there is a console handler.
* `logger.enable(level="WARNING")` added the default console handler back, with `WARNING` as its minimum level. Without `level`, it starts again at `DEBUG`.

This is handy in tests, or in a command line tool with a `--quiet` flag. Handlers that write to files keep working while the console is off.

/// warning

`disable()` removes **every** console handler, including the ones you added for `sys.stdout` or `sys.stderr` with your own format. `enable()` then brings back the **default** handler, not yours.

If you need to switch a custom console handler on and off, keep its ID and use `remove()` and `add()`, as shown in [Handlers and Sinks](sinks.md).

`enable(level=...)` only sets the level when it adds the handler back. If the console is already on, use `set_level()`.

///

/// tip

`disable()` and `enable()` also accept a **module name**, like `logger.disable("mylib")`, to silence the messages of a single library. That is covered in the Advanced User Guide, in [library logging](../advanced/library-logging.md).

///

## Recap { #recap }

* There are eight built-in levels: `TRACE`, `DEBUG`, `INFO`, `SUCCESS`, `WARNING`, `ERROR`, `FAIL` and `CRITICAL`, each with its own method.
* `set_level("WARNING")` or `set_level(LogLevel.Warning)` sets the minimum level of the console.
* `get_level()` returns the current console level, `is_level_enabled()` tells you if a level would be logged anywhere.
* Use `is_level_enabled()` to skip expensive work for messages nobody will see.
* `logger.log(level, message)` logs at a level chosen at runtime.
* `disable()` and `enable()` turn the console output off and on.
