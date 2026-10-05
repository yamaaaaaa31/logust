# Log Levels

Use levels to control verbosity, and add your own when needed.

## Built-in levels

| Level | Value | Color | Description |
|-------|-------|-------|-------------|
| TRACE | 5 | Cyan | Detailed debugging information |
| DEBUG | 10 | Blue | Debug information |
| INFO | 20 | White | General information |
| SUCCESS | 25 | Green | Success messages |
| WARNING | 30 | Yellow | Warning messages |
| ERROR | 40 | Red | Error messages |
| FAIL | 45 | Red | Failure messages |
| CRITICAL | 50 | Red (bold) | Critical errors |

!!! tip "Guard expensive logs"
    Use `is_level_enabled()` before doing heavy work.

    ```python
    from logust import logger

    if logger.is_level_enabled("DEBUG"):
        value = expensive_call()
        logger.debug(f"Computed value: {value}")
    ```

## Set the minimum level

=== "Enum"
    ```python
    from logust import logger, LogLevel

    logger.set_level(LogLevel.Warning)
    ```

=== "String"
    ```python
    from logust import logger

    logger.set_level("warning")
    logger.set_level("WARNING")
    ```

## Check current level

```python
from logust import logger

current = logger.get_level()
print(f"Current level: {current.name}")
```

## Custom levels

```python
from logust import logger

logger.level("NOTICE", no=25, color="cyan", icon="!")
logger.log("NOTICE", "This is a notice")
```

### Custom level parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | str | Level name (uppercase recommended) |
| `no` | int | Numeric severity (higher = more severe) |
| `color` | str | Color name for console output |
| `icon` | str | Icon symbol (optional), shown by `{level.icon}` |

### Level icons

`{level.icon}` in a format shows the level's icon, `{level.no}` its severity:

```python
logger.add("app.log", format="{level.icon} {level.name:<8} | {message}")
```

Built-in levels use loguru's default icons:

| Level | Icon | | Level | Icon |
|-------|------|-|-------|------|
| TRACE | ✏️ | | WARNING | ⚠️ |
| DEBUG | 🐞 | | ERROR | ❌ |
| INFO | ℹ️ | | FAIL | ✖️ |
| SUCCESS | ✅ | | CRITICAL | ☠️ |

`FAIL` is Logust-only, so its icon has no loguru counterpart. A custom level without
`icon` renders `{level.icon}` as an empty string.

### Look up or update a level

Call `level()` with only a name to get its information, or without `no` to
update the color or icon of an existing level (built-in levels included).
Every call returns a `Level(name, no, color, icon)` named tuple.

```python
from logust import logger

logger.level("INFO")
# Level(name='INFO', no=20, color='green', icon='ℹ️')

logger.level("INFO", color="blue")  # Built-in INFO is now blue on the console
logger.level("NOTICE", icon="*")  # Keeps NOTICE's severity and color

logger.level("MISSING")  # ValueError: Level 'MISSING' does not exist
```

The same works in `configure(levels=[{"name": "INFO", "color": "blue"}])`.

### Available colors

- `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`
- Bright variants: `bright_red`, `bright_green`, etc.

## Enable or disable console

```python
from logust import logger

logger.disable()
logger.info("This will not appear in console")

logger.enable()  # Re-enable with previous level
logger.enable(level="INFO")  # Re-enable and set minimum level
```

The `enable()` method accepts an optional `level` parameter to set the minimum console level when re-enabling.

## Enable or disable modules

As in loguru, `disable(name)` drops every message logged from the module `name` and its submodules, and `enable(name)` turns them back on. This is how a library keeps its logs quiet until the application opts in:

```python
# mylib/__init__.py
from logust import logger

logger.disable("mylib")  # Silent by default


def work():
    logger.info("Working")  # Dropped unless the application enables "mylib"
```

```python
# Application
from logust import logger
import mylib

logger.enable("mylib")  # Show mylib's messages again
mylib.work()
```

Rules:

- The name is matched against the caller's module (`record["name"]`, the module's `__name__`) on dotted boundaries: `disable("mylib")` covers `mylib` and `mylib.sub`, not `mylibrary`.
- The most specific rule wins: after `disable("mylib")` and `enable("mylib.api")`, only `mylib.api` (and its submodules) logs. Enabling or disabling a module replaces the rules of its submodules.
- `disable("")` disables every module and `enable("")` removes every rule.
- Rules are shared by `logger`, `logust.enable()` / `logust.disable()`, and every logger created with `bind()` or `patch()`. They apply to all logging methods, `log()`, `exception()`, `opt()` and `catch()`. With `opt(lazy=True)`, lazy arguments of a disabled module are not evaluated.
- `configure(activation=[("mylib", False), ("mylib.api", True)])` applies rules in order.
- Records forwarded by `InterceptHandler` from the standard `logging` module are matched against the stdlib logger name (for example `logger.disable("urllib3")`).

While no module is disabled, logging calls skip this check entirely. Once a rule exists, each message looks up its module in a cache, so the cost is one frame lookup and one dictionary lookup.

### Level names versus module names

`enable()` and `disable()` without a name keep their console behavior (see above). A string passed to `enable()` is treated as a level when it is a built-in level name (case-insensitive `trace`, `debug`, `info`, `success`, `warning`, `error`, `fail`, `critical`) and as a module name otherwise:

```python
logger.enable("INFO")   # Re-enable the console at INFO
logger.enable("mylib")  # Enable the mylib module
```

A top-level module named like a built-in level (for example a module called `error`) can be disabled with `disable("error")`, but `enable("error")` re-enables the console. Use `enable("")` to clear the rule in that case.
