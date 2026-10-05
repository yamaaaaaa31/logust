# Formatting

Make logs readable with templates, or switch to JSON.

!!! example "JSON for log aggregation"
    Use `serialize=True` for structured logging with Elasticsearch, Loki, etc.

## Default format

The default log format includes caller information (module, function, line number):

```
{time} | {level:<8} | {name}:{function}:{line} - {message}
```

Output:
```
2025-12-24 15:52:42.199 | INFO     | __main__:my_function:10 - Hello, Logust!
```

This format is similar to uvicorn's log format, making it easy to identify where each log message originated.

## Custom format

Customize the format when adding a handler:

```python
from logust import logger

logger.add("app.log", format="{time} | {level} | {message}")
logger.add("simple.log", format="[{level}] {message}")
logger.add("minimal.log", format="{message}")
```

## Message arguments

Like loguru, the message is formatted with `str.format()` when you pass arguments:

```python
logger.info("Processed {} items in {:.2f}s", 42, 1.234)
logger.info("User {user} logged in", user="alice")
logger.info("{} by {user}", "login", user="alice", request_id="r1")
```

- Keyword arguments that are not used by a placeholder are added to `extra`
  (`request_id` above).
- A message logged without arguments is never formatted, so
  `logger.info("dict: {}")` prints the braces as-is.
- A missing placeholder value raises `IndexError` or `KeyError`, the same as
  `str.format()`.
- When the level is filtered out, the arguments are not formatted at all.

## Format tokens

| Token | Description | Example |
|-------|-------------|---------|
| `{time}` | Timestamp | `2025-12-24 12:00:00.123` |
| `{time:<spec>}` | Timestamp in a [custom format](#time-formatting) | `{time:HH:mm:ss}` → `12:00:00` |
| `{level}`, `{level.name}` | Log level name | `INFO` |
| `{level:<8}`, `{level.name:<8}` | Aligned level (width 8) | `INFO    ` |
| `{level.no}` | Numeric severity | `20` |
| `{level.icon}` | Level icon ([defaults](levels.md#level-icons)) | `ℹ️` |
| `{message}` | Log message | `Hello, world!` |
| `{name}`, `{module}` | Module/logger name | `__main__`, `myapp.utils` |
| `{function}` | Function name | `process_request` |
| `{line}` | Line number | `42` |
| `{file}`, `{file.name}` | Source file name | `handler.py` |
| `{file.path}` | Source file path | `/srv/myapp/handler.py` |
| `{thread}` | Thread name and id | `MainThread:8601235520` |
| `{thread.name}`, `{thread.id}` | Thread name / id | `MainThread`, `8601235520` |
| `{process}` | Process name and id | `MainProcess:4242` |
| `{process.name}`, `{process.id}` | Process name / id | `MainProcess`, `4242` |
| `{elapsed}` | Time since logger start | `00:01:23.456` |
| `{exception}` | Formatted traceback (empty without one), see [below](#exceptions-in-the-format) | |
| `{extra[key]}` | Extra context fields | `{extra[user_id]}` |
| `{extra}` | All extra fields, [like loguru](#all-extra-fields) | `{'user_id': '123'}` |

Placeholders that are not in this table (for example `{level.color}`) are written as is.

Logust only collects what the format uses: caller info for `{name}`, `{function}`, `{line}`,
and `{file*}`, thread info for `{thread*}`, process info for `{process*}`.

### Time formatting

`{time:<spec>}` takes [loguru's time tokens](https://loguru.readthedocs.io/en/stable/api/logger.html#time):

```python
logger.add("app.log", format="{time:YYYY-MM-DD HH:mm:ss.SSS ZZ} | {level} | {message}")
# 2025-12-24 12:00:00.123 +0900 | INFO | Hello
```

| Token | Output | | Token | Output |
|-------|--------|-|-------|--------|
| `YYYY` / `YY` | `2025` / `25` | | `HH` / `H` | Hour `09` / `9` |
| `Q` | Quarter `1`-`4` | | `hh` / `h` | 12-hour clock `09` / `9` |
| `MMMM` / `MMM` | `December` / `Dec` | | `mm` / `m` | Minute `05` / `5` |
| `MM` / `M` | `03` / `3` | | `ss` / `s` | Second `07` / `7` |
| `DDDD` / `DDD` | Day of year `058` / `58` | | `S` … `SSSSSS` | Fraction of second, 1 to 6 digits |
| `DD` / `D` | Day of month `05` / `5` | | `A` | `AM` / `PM` |
| `dddd` / `ddd` | `Monday` / `Mon` | | `Z` / `ZZ` | UTC offset `+09:00` / `+0900` |
| `d` / `E` | Weekday, Monday `0` / `1` | | `zz` | Time zone name (see below) |
| `X` / `x` | Unix time in seconds / microseconds | | | |

- Wrap a token in brackets to write it literally: `{time:[YYYY]}` gives `YYYY`.
- End the spec with `!UTC` to convert to UTC first: `{time:HH:mm!UTC}`.
- A spec containing `%` is a strftime format: `{time:%Y-%m-%d %H:%M:%S.%f}`.
- `{time:}` (empty spec) gives ISO 8601: `2025-12-24T12:00:00.123456+0900`.
- An invalid spec (more than six `S`, an unknown `%` directive) raises `ValueError` in `add()`.

Plain `{time}` is unchanged: `2025-12-24 12:00:00.123` in file and console sinks, the
record's RFC 3339 timestamp in callable sinks. `{time:<spec>}` gives the same output in all of them.

!!! note "Differences from loguru"
    `zz` gives `UTC` with `!UTC`, otherwise the UTC offset (`+09:00`), since Logust has
    no time zone abbreviation for local time. Month and day names are always English.

### Exceptions in the format

Without `{exception}`, a traceback is appended on its own line after the formatted
message. With `{exception}`, the traceback is written at that position and nothing
is appended, so it is never printed twice:

```python
logger.add("app.log", format="{time} | {level} | {message}\n{exception}")
```

`{exception}` is empty for records without an exception. loguru appends
`"\n{exception}"` to every string format, so a loguru format with `{exception}`
prints the traceback twice; Logust prints it once.

### Caller information

The `{name}`, `{function}`, and `{line}` tokens capture the call site:

```python
# myapp/handler.py, line 15
def handle_request():
    logger.info("Processing request")
    # Output: myapp.handler:handle_request:15 - Processing request
```

When using `opt(depth=N)`, caller info is adjusted to skip N frames:

```python
def wrapper():
    def inner():
        logger.opt(depth=1).info("From wrapper")  # Shows 'wrapper', not 'inner'
    inner()
```

### Extra fields

```python
from logust import logger

user_logger = logger.bind(user_id="123", action="login")
user_logger.info("User action")
```

Format usage:

```text
{time} | {level} | {message} | user={extra[user_id]}
```

#### All extra fields

`{extra}` writes the whole extra dict, as `str(dict)` does in loguru:

```python
logger.add(sys.stderr, format="{message} {extra}")
logger.bind(user="alice", attempt=2).info("Login")
# Login {'attempt': 2, 'user': 'alice'}
```

Strings are quoted like `repr()`. `int`, `float`, `bool`, `None`, lists,
tuples and dicts look the same as in loguru. Differences from loguru:

- Keys are sorted. loguru keeps the order in which they were bound.
- Other types are written with `str()`: a `datetime` reads
  `2024-01-02 03:04:05` instead of `datetime.datetime(2024, 1, 2, 3, 4, 5)`.
- `{extra:<spec>}` is not supported and is written as is.

## JSON output

For structured logging, use the `serialize` option:

```python
logger.add("app.json", serialize=True)

def handle_login():
    logger.info("User logged in")

handle_login()
```

Output:
```json
{
  "time": "2025-12-24 12:00:00.123",
  "level": "INFO",
  "message": "User logged in",
  "name": "__main__",
  "function": "handle_login",
  "line": 5
}
```

Caller information is automatically included in JSON output.

### JSON with context

When using `bind()`, extra fields are included:

```python
logger.add("app.json", serialize=True)
user_logger = logger.bind(user_id="123", action="login")
user_logger.info("User action")
```

Output:
```json
{
  "time": "2025-12-24T12:00:00.123456",
  "level": "INFO",
  "message": "User action",
  "extra": {
    "user_id": "123",
    "action": "login"
  }
}
```

`serialize=True` keeps common extra values typed in JSON while preserving
`str(value)` output for `{extra[key]}` format tokens and Python callbacks.

| Python extra type | JSON output |
|-------------------|-------------|
| `None`, `bool`, `str`, `int`, `float` | Native JSON null, boolean, string, or number |
| `list`, `tuple`, `set`, `frozenset` | JSON array |
| `dict` | JSON object with stringified keys |
| `bytes`, `bytearray` | UTF-8 string with invalid bytes replaced |
| `datetime`, `date`, `time` | `.isoformat()` string |
| `Enum` | `.value`, converted with the same rules |

Other objects, including `Decimal`, `UUID`, `Path`, and `complex`, fall back to
`str(value)` in JSON.

## Color markup

Add colors to console output using markup:

```python
from logust import logger

logger.info("<red>Error</red> in <blue>module</blue>")
logger.info("<green>Success!</green>")
logger.info("<bold>Important</bold> message")
```

### Available tags

| Tag | Description |
|-----|-------------|
| `<red>`, `<green>`, `<blue>`, etc. | Text colors |
| `<bold>` | Bold text |
| `<underline>` | Underlined text |
| `<bright_red>`, `<bright_green>`, etc. | Bright colors |

Markup is rendered on sinks with `colorize=True` and stripped from the
others. Unknown tags are written as is.

### Markup as plain text

loguru only parses markup in a message with `opt(colors=True)`. logust always
parses it (as in earlier releases), and `opt(colors=False)` keeps the tags of
that message as plain text on every sink:

```python
logger.opt(colors=False).info("Literal <red>tags</red>")
# Literal <red>tags</red>
```

`opt(colors=True)` is accepted and behaves like the default.
