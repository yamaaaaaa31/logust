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
| `icon` | str | Icon symbol (optional) |

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
