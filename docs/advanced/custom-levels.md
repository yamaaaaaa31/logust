# Custom Levels { #custom-levels }

The eight built-in levels cover most needs. But sometimes you want a level that means something specific to **your** app: a `NOTICE` between `INFO` and `WARNING`, an `AUDIT` level for security events, a `METRIC` level...

You can create your own levels with `logger.level()`, and use them like the built-in ones.

## Define a level { #define-a-level }

Call `logger.level()` with a name and a **severity number** (`no`), then log with `logger.log()`:

```python hl_lines="3 6"
--8<-- "docs_src/advanced_custom_levels/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:01:07.965 | INFO     | __main__:<module>:5 - Deploying version 2.4.0
2026-10-06 12:01:07.965 | NOTICE   | __main__:<module>:6 - Feature flag 'new-checkout' is now on
2026-10-06 12:01:07.965 | WARNING  | __main__:<module>:7 - The cache is cold
```

</div>

On a terminal, the `NOTICE` line is printed in cyan. 🎉

The parameters are:

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | The level name. Names are case-insensitive, uppercase is the convention. |
| `no` | `int` | The severity. A higher number is more severe. |
| `color` | `str` | The color of the level on the console (see [Available colors](#available-colors)). |
| `icon` | `str` | An optional icon, shown by `{level.icon}` in a format. |

### Choosing the number { #choosing-the-number }

The number decides where your level sits among the built-in ones:

| Level | `no` |
|-------|------|
| `TRACE` | 5 |
| `DEBUG` | 10 |
| `INFO` | 20 |
| `SUCCESS` | 25 |
| `WARNING` | 30 |
| `ERROR` | 40 |
| `FAIL` | 45 |
| `CRITICAL` | 50 |

`NOTICE` with `no=23` is a bit more important than `INFO`, and less than `SUCCESS` and `WARNING`. A handler that shows `INFO` and above also shows `NOTICE`, and a handler that only shows `WARNING` and above hides it.

/// tip

Pick a number that no built-in level uses. `logger.log(25, ...)` always means `SUCCESS`, even if you registered a custom level with `no=25`, so a free number keeps "log by number" unambiguous.

///

## Look up a level { #look-up-a-level }

Call `logger.level()` with **only a name** to get the level's information back. Every call to `logger.level()` returns a `Level` named tuple with `name`, `no`, `color` and `icon`:

```python hl_lines="5-6"
--8<-- "docs_src/advanced_custom_levels/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

Level(name='NOTICE', no=23, color='cyan', icon='🔔')
23
Level(name='NOTICE', no=23, color='cyan', icon='📣')
Level(name='INFO', no=20, color='blue', icon='ℹ️')
```

</div>

Notice that `logger.level("notice")` finds `NOTICE`: level names are case-insensitive.

Looking up a level that doesn't exist raises a `ValueError`:

```python
logger.level("MISSING")  # ValueError: Level 'MISSING' does not exist
```

## Update a level { #update-a-level }

Call `logger.level()` with a name and a `color` and/or `icon`, but **without** `no`, to change an existing level. The other values are kept.

That's what lines 8 and 9 of the example above do:

* `logger.level("NOTICE", icon="📣")` gives `NOTICE` a new icon, and keeps its number and color.
* `logger.level("INFO", color="blue")` works on **built-in** levels too: `INFO` is now blue on the console.

You can also call `logger.level()` again **with** `no` to re-register a custom level with a new number:

```python
logger.level("NOTICE", no=24)  # NOTICE is now 24, color and icon are kept
```

Built-in levels keep their numbers, though. Changing one raises a `TypeError`:

```python
logger.level("INFO", no=21)
# TypeError: Level 'INFO' already exists, you can't update its severity no
```

/// note | Technical Details

`Level.color` is a color name like `"cyan"`. In loguru it's a markup string like `"<cyan><bold>"`. And unlike loguru, passing `no` for an existing custom level re-registers it instead of raising.

///

## Icons and numbers in a format { #icons-and-numbers-in-a-format }

The level of each record has an `icon`, a `name` and a `no`. You can use all of them in a [format](../tutorial/formatting.md):

```python hl_lines="6"
--8<-- "docs_src/advanced_custom_levels/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

ℹ️ INFO     (20) | Deploying version 2.4.0
🔔 NOTICE   (23) | Feature flag 'new-checkout' is now on
✅ SUCCESS  (25) | Deployed
```

</div>

Built-in levels use loguru's default icons:

| Level | Icon | | Level | Icon |
|-------|------|-|-------|------|
| `TRACE` | ✏️ | | `WARNING` | ⚠️ |
| `DEBUG` | 🐞 | | `ERROR` | ❌ |
| `INFO` | ℹ️ | | `FAIL` | ✖️ |
| `SUCCESS` | ✅ | | `CRITICAL` | ☠️ |

`FAIL` is a Logust-only level, so its icon has no loguru counterpart. A custom level without an `icon` renders `{level.icon}` as an empty string.

## Available colors { #available-colors }

These names work for `color=`:

* `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`
* `bright_red`, `bright_green`, `bright_yellow`, `bright_blue`, `bright_magenta`, `bright_cyan`, `bright_white`

/// warning

An unknown color name is not an error: the level is shown in white. If your level doesn't get the color you expected, check the spelling. 🤓

///

The built-in levels use `cyan` (`TRACE`), `blue` (`DEBUG`), `green` (`INFO`), `bright_green` (`SUCCESS`), `yellow` (`WARNING`), `red` (`ERROR`), `magenta` (`FAIL`) and `bright_red` (`CRITICAL`).

## Logging with a custom level { #logging-with-a-custom-level }

There is no `logger.notice()` method. Custom levels are logged with `logger.log()`, by **name** or by **number**:

```python
logger.log("NOTICE", "By name")
logger.log("notice", "Also by name, names are case-insensitive")
logger.log(23, "By number")
```

`logger.log()` accepts the same [message arguments](../tutorial/message-arguments.md) as the other methods:

```python
logger.log("NOTICE", "Deployed {} to {region}", "v2.4.0", region="eu-west-1")
```

And it works with [`opt()`](opt.md) too, for example `logger.opt(lazy=True).log("NOTICE", ...)`.

A level name that was never registered raises a `ValueError`:

```python
logger.log("NOPE", "Unknown level")  # ValueError: Invalid log level
```

## Filtering by a custom level { #filtering-by-a-custom-level }

A custom level works as a threshold anywhere a level is: pass its name to `level=`, and the handler takes that level and everything above it:

```python hl_lines="8"
--8<-- "docs_src/advanced_custom_levels/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

NOTICE   | Feature flag 'new-checkout' is now on
NOTICE   | The same level, by number
WARNING  | The cache is cold
```

</div>

A record passes when its level number is at least the threshold's: `NOTICE` is 23, so the handler keeps `NOTICE` (23) and `WARNING` (30), and drops `INFO` (20).

The same goes for every `level=` option: `logger.add(level=...)` for every kind of sink, `logger.set_level()`, `logger.enable(level=...)`, `logger.add_callback(level=...)`, `logger.is_level_enabled()` and the `"level"` key of `logger.configure(handlers=[...])`. Each one accepts:

* A level name, built-in or custom, in any case: `"WARNING"`, `"notice"`.
* A number, `0` or more: `level=23`. It doesn't have to be a registered level.
* A `LogLevel` member: `level=LogLevel.Warning`.

`logger.enable()` takes a custom level as a keyword only: `logger.enable(level="NOTICE")`. A positional name that is not a built-in level is a module name, so `logger.enable("NOTICE")` re-enables a module called `NOTICE`.

The comparison is always by number, so built-in and custom levels mix freely. With `level="SUCCESS"` (25) a handler shows custom levels from 25 up, and with `level="NOTICE"` it shows `SUCCESS` too.

Register a level before you use it as a threshold. A name that doesn't exist raises a `ValueError` (`Level 'NOPE' does not exist`), and so does a negative number. Any other type raises a `TypeError`.

## Levels in configure() { #levels-in-configure }

If you set up logging with `logger.configure()`, you can declare and update levels in the same place, with the same rules as `logger.level()`:

```python
logger.configure(
    levels=[
        {"name": "NOTICE", "no": 23, "color": "cyan", "icon": "🔔"},
        {"name": "INFO", "color": "blue"},
    ],
)
```

## Recap { #recap }

* `logger.level("NOTICE", no=23, color="cyan", icon="🔔")` creates a level.
* `logger.level("NOTICE")` looks it up, and returns a `Level(name, no, color, icon)`.
* `logger.level("INFO", color="blue")` updates a level, built-in ones included.
* Log with `logger.log("NOTICE", ...)` or `logger.log(23, ...)`.
* `{level.icon}`, `{level.name}` and `{level.no}` show the level in a format.
* `level="NOTICE"` (or `level=23`) starts a handler at a custom level, and `logger.set_level("NOTICE")` does the same for the console.
