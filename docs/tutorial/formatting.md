# Formatting { #formatting }

Every sink turns a record into a line of text. The **format** decides what that line looks like.

Logust has a sensible default, and you can change it per sink with a small template language that will feel familiar if you have used `str.format()` or loguru.

## The default format { #the-default-format }

Let's start with what you get without configuring anything:

```python
--8<-- "docs_src/formatting/tutorial001.py"
```

Run it:

<div class="termy">

```console
$ python main.py

2026-10-06 11:59:13.505 | INFO     | __main__:connect:5 - Connecting to the database
2026-10-06 11:59:13.505 | WARNING  | __main__:<module>:9 - Running without a cache
```

</div>

Each line is built from this template:

```
{time} | {level:<8} | {name}:{function}:{line} - {message}
```

* `{time}`: when the record was created, in local time, with milliseconds.
* `{level:<8}`: the level name, padded to 8 characters so the columns line up.
* `{name}:{function}:{line}`: **where** the call happened. The module (`__main__`), the function (`connect`, or `<module>` for top-level code) and the line number.
* `{message}`: your message.

The layout is close to uvicorn's, so it should feel at home next to your web server logs. 😎

/// tip

The default sink also adds colors: the time is dimmed, the level gets its own color, and the caller information is cyan. You will see how to color your own formats in [Colors](#colors).

///

## A custom format { #a-custom-format }

To use your own layout, pass `format=` to `logger.add()`:

```python hl_lines="6"
--8<-- "docs_src/formatting/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 11:59:13.540 | INFO | Server started
2026-10-06 11:59:13.541 | WARNING | Disk usage is at 91%
```

</div>

The format is a template string. Each `{placeholder}` is replaced with a value from the record, and everything else is copied as is.

`format=` is an option of each sink, so you can have a short format on the console and a detailed one in a file at the same time:

```python
logger.add(sys.stderr, format="{level} | {message}")
logger.add("app.log", format="{time} | {level:<8} | {name}:{function}:{line} - {message}")
```

/// info

The format is applied to the **record**. The `{}` in your *message* (`"Disk usage is at {}%"`) is a different thing: it is filled from the arguments of the logging call, as you saw in [Message Arguments](message-arguments.md).

///

## Format tokens { #format-tokens }

Here are all the placeholders you can use in a format:

| Token | Description | Example |
|-------|-------------|---------|
| `{time}` | Timestamp | `2026-10-06 12:00:00.123` |
| `{time:<spec>}` | Timestamp in a [custom format](#time-formatting) | `{time:HH:mm:ss}` → `12:00:00` |
| `{level}`, `{level.name}` | Level name | `INFO` |
| `{level:<8}`, `{level.name:<8}` | Level name padded to a width (any token takes a [format spec](#format-specs)) | `INFO    ` |
| `{level.no}` | Numeric severity | `20` |
| `{level.icon}` | Level icon | `ℹ️` |
| `{message}` | The message | `Server started` |
| `{name}` | Module `__name__` of the caller | `__main__`, `myapp.utils` |
| `{module}` | Caller file name without extension | `utils` |
| `{function}` | Caller function | `load_config` |
| `{line}` | Caller line number | `42` |
| `{file}`, `{file.name}` | Caller file name | `main.py` |
| `{file.path}` | Caller file full path | `/srv/myapp/main.py` |
| `{thread}` | Thread name and id | `MainThread:8348778368` |
| `{thread.name}`, `{thread.id}` | Thread name / id | `MainThread`, `8348778368` |
| `{process}` | Process name and id | `MainProcess:16807` |
| `{process.name}`, `{process.id}` | Process name / id | `MainProcess`, `16807` |
| `{elapsed}` | Time since Logust was started | `00:01:23.456` |
| `{extra[key]}` | One value of the [context](#extra-fields) | `{extra[user_id]}` → `42` |
| `{extra}` | All the context values | `{'user_id': 42}` |
| `{exception}` | The traceback, see [Exceptions in the format](#exceptions-in-the-format) | |

Placeholders that are not in this table (for example `{level.color}`) are written as is.

/// tip | Performance

Logust only collects what your formats use. Finding the caller (`{name}`, `{function}`, `{line}`, `{file}`...) costs a bit of time on every call, and thread and process information too. If no sink uses those tokens, Logust doesn't look them up at all. 🚀

///

### Caller information { #caller-information }

Let's use some of them:

```python hl_lines="6"
--8<-- "docs_src/formatting/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

DEBUG    | main.py:10 in load_config() | Reading settings.toml
SUCCESS  | main.py:11 in load_config() | Configuration loaded
CRITICAL | main.py:15 in <module>() | Shutting down
```

</div>

The caller is the line that called `logger.debug()`, `logger.success()` and so on, so you can jump straight to it in your editor.

/// tip

If you write a helper function that logs for its caller, the caller info would point at the helper. `logger.opt(depth=1)` moves it one frame up. You will see it in [The opt() Method](../advanced/opt.md).

///

### Aligning the level { #aligning-the-level }

Notice the `{level:<8}` in the example above. The `:<8` part is a **format spec**: it pads the level name with spaces to 8 characters, left-aligned, so `DEBUG`, `SUCCESS` and `CRITICAL` all start the message at the same column.

8 is the length of the longest built-in level name, `CRITICAL`.

### Format specs { #format-specs }

Every token except `{time}` (which has [its own specs](#time-formatting)) and `{extra}` takes a spec from Python's [format-spec mini-language](https://docs.python.org/3/library/string.html#formatspec), the same one `format()` and f-strings use. The output is exactly what `format(value, spec)` gives in Python, in every kind of sink:

```python hl_lines="8"
--8<-- "docs_src/formatting/tutorial011.py"
```

<div class="termy">

```console
$ python main.py

[  INFO   ] line 011 | ann   | Short message
[ WARNING ] line 012 | bob   | A message that is much too lon
[  ERROR  ] line 013 | zoë   | Disk full 💾
```

</div>

A spec is `[[fill]align][sign][z][#][0][width][grouping][.precision][type]`. The most useful parts:

| Spec | Meaning | Example | Output |
|------|---------|---------|--------|
| `<N`, `>N`, `^N` | Align left, right or center in `N` characters | `{level:>8}` | `    INFO` |
| `<fill><align>N` | Pad with another character | `{level:*^10}` | `***INFO***` |
| `.N` | Cut text to `N` characters | `{message:.10}` | `A message ` |
| `0N`, `0Nd` | Pad a number with zeros | `{line:05d}` | `00042` |
| `,`, `_` | Group thousands | `{thread.id:,}` | `8,348,778,368` |
| `x`, `X`, `o`, `b` | Hexadecimal, octal, binary (`#` adds `0x`...) | `{line:#x}` | `0x2a` |
| `+` | Always show the sign | `{level.no:+}` | `+20` |
| `e`, `f`, `g`, `%` | As a float | `{line:.1f}` | `42.0` |

`{line}`, `{level.no}`, `{thread.id}` and `{process.id}` are integers. All the other tokens are strings, including `{thread}` (`MainThread:8348778368`) and `{elapsed}` (`00:01:23.456`).

loguru's default format pads the level with `{level: <8}`, an explicit space fill: it works too. Widths count characters (Unicode code points, like `len()`), so `é` and `💾` count as one. A wide character such as `日` also counts as one, even though a terminal shows it two columns wide.

The spec is checked when you add the sink. A spec Python would reject raises `ValueError` right away, in `logger.add()`, with Python's message:

```python
logger.add("app.log", format="{message:d}")
# ValueError: Unknown format code 'd' for object of type 'str' (format field '{message:d}')
```

/// note | `{extra[key]}` values

A context value is formatted from its text, `str(value)`, as it is written without a spec. So string specs like `{extra[user]:<8}` or `{extra[path]:.20}` work for any value, but number specs don't: `{extra[count]:05d}` writes `42`, unformatted, where loguru writes `00042`. A spec that no value could accept, like `{extra[count]:abc}`, raises `ValueError` in `logger.add()`.

///

With colors, padding is computed on the text without its color codes, so colored columns line up too. A `{message}` with [color markup](#colors) is padded on its visible text; if a precision cuts it, its colors are dropped.

### Time formatting { #time-formatting }

`{time}` alone gives `2026-10-06 11:59:13.505`. Put a spec after a colon to choose your own layout. Logust uses [loguru's time tokens](https://loguru.readthedocs.io/en/stable/api/logger.html#time):

```python hl_lines="6-9"
--8<-- "docs_src/formatting/tutorial004.py"
```

Four sinks, one message, four timestamps:

<div class="termy">

```console
$ python main.py

2026-10-06 11:59:13.616 +0900 | Same moment, four formats
02:59:13 UTC | Same moment, four formats
Tuesday 6 October 2026, 11:59 AM | Same moment, four formats
06/10/2026 11:59 | Same moment, four formats
```

</div>

These are the tokens you can use:

| Token | Output | | Token | Output |
|-------|--------|-|-------|--------|
| `YYYY` / `YY` | `2026` / `26` | | `HH` / `H` | Hour `09` / `9` |
| `Q` | Quarter `1`-`4` | | `hh` / `h` | 12-hour clock `09` / `9` |
| `MMMM` / `MMM` | `October` / `Oct` | | `mm` / `m` | Minute `05` / `5` |
| `MM` / `M` | `03` / `3` | | `ss` / `s` | Second `07` / `7` |
| `DDDD` / `DDD` | Day of year `058` / `58` | | `S` … `SSSSSS` | Fraction of second, 1 to 6 digits |
| `DD` / `D` | Day of month `05` / `5` | | `A` | `AM` / `PM` |
| `dddd` / `ddd` | `Monday` / `Mon` | | `Z` / `ZZ` | UTC offset `+09:00` / `+0900` |
| `d` / `E` | Weekday, Monday is `0` / `1` | | `zz` | Time zone name (see below) |
| `X` / `x` | Unix time in seconds / microseconds | | | |

A few more rules:

* Wrap text in brackets to write it literally: `{time:[YYYY]}` gives `YYYY`.
* End the spec with `!UTC` to convert to UTC first: `{time:HH:mm:ss!UTC}`.
* A spec containing `%` is a `strftime` format instead: `{time:%d/%m/%Y %H:%M}`.
* An empty spec, `{time:}`, gives ISO 8601: `2026-10-06T11:59:13.616504+0900`.
* An invalid spec (more than six `S`, an unknown `%` directive) raises `ValueError` right away, in `logger.add()`, not later when you log.

/// note | Differences from loguru

`zz` gives `UTC` with `!UTC`, and the UTC offset (`+09:00`) otherwise, because Logust has no time zone abbreviation for local time. Month and day names are always in English.

///

/// info

In callable sinks, a plain `{time}` is the record's RFC 3339 timestamp (`2026-10-06T11:59:13.616504+09:00`) instead of `2026-10-06 11:59:13.616`. `{time:<spec>}` gives the same output in every kind of sink.

///

### Threads, processes and elapsed time { #threads-processes-and-elapsed-time }

When several threads or processes write to the same log, it helps to see which one wrote each line:

```python hl_lines="8"
--8<-- "docs_src/formatting/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

00:00:00.000 | MainProcess | MainThread | Starting
00:00:00.000 | MainProcess | downloader | Downloading in the background
00:00:00.204 | MainProcess | MainThread | Done
```

</div>

`{elapsed}` is the time since Logust was started (when your program imported it), as `HH:MM:SS.mmm`. It is a quick way to see how long things take without doing arithmetic on timestamps.

## Extra fields { #extra-fields }

Records can carry **extra** values: the context you attach with `bind()`, and keyword arguments that are not used by the message. You will learn all about them in [Adding Context](context.md). For now, let's see how to show them.

### One value with `{extra[key]}` { #one-value-with-extra-key }

```python hl_lines="6 8"
--8<-- "docs_src/formatting/tutorial006.py"
```

<div class="termy">

```console
$ python main.py

INFO | Profile updated | user=42
INFO | Anonymous visit | user=
```

</div>

When a record doesn't have the key, `{extra[user_id]}` is empty. No error, no crash, the line is still written. With a [format spec](#format-specs), the empty value is still padded: `{extra[user_id]:<6}` keeps the column.

### All values with `{extra}` { #all-values-with-extra }

`{extra}` writes the whole extra dict, like `str(dict)` does in loguru:

```python hl_lines="6"
--8<-- "docs_src/formatting/tutorial007.py"
```

<div class="termy">

```console
$ python main.py

INFO | Login {'attempt': 2, 'user': 'alice'}
INFO | Payment received {'amount': 9.99, 'order_id': 1234}
INFO | No context here {}
```

</div>

Strings are quoted like `repr()`. `int`, `float`, `bool`, `None`, lists, tuples and dicts look the same as in loguru.

/// note | Differences from loguru

* Keys are sorted. loguru keeps the order in which they were bound.
* Other types are written with `str()`: a `datetime` reads `2024-01-02 03:04:05` instead of `datetime.datetime(2024, 1, 2, 3, 4, 5)`.
* `{extra:<spec>}` is not supported and is written as is.

///

## Exceptions in the format { #exceptions-in-the-format }

When a record carries an exception (you will see how in [Logging Exceptions](exceptions.md)), Logust writes the traceback on its own lines **after** the formatted message.

If you want to decide where it goes, put `{exception}` in the format:

```python hl_lines="6"
--8<-- "docs_src/formatting/tutorial008.py"
```

<div class="termy">

```console
$ python main.py

INFO | Starting the import

ERROR | Import failed
Traceback (most recent call last):
  File "/home/user/project/main.py", line 10, in <module>
    rows = 100 / 0
           ~~~~^~~
ZeroDivisionError: division by zero

```

</div>

With `{exception}` in the format, the traceback is written at that position and nothing is appended, so it is never printed twice. For records without an exception, `{exception}` is empty.

That's why `INFO | Starting the import` is followed by an empty line here: the `\n` before `{exception}` is still part of the format. If you don't want that, leave `{exception}` out and let Logust append the traceback for you.

/// info

loguru appends `"\n{exception}"` to every string format, so a loguru format that already contains `{exception}` prints the traceback twice. Logust prints it once.

///

## Colors { #colors }

Logust understands loguru-style **color markup**: tags like `<red>...</red>` that become ANSI color codes on a terminal.

### Colors in the format { #colors-in-the-format }

Wrap parts of the format in tags:

```python hl_lines="8-10"
--8<-- "docs_src/formatting/tutorial009.py"
```

<div class="termy">

```console
$ python main.py

11:59:13 | INFO     | __main__ - Colors in the format
11:59:13 | ERROR    | __main__ - The level tag follows the level color
```

</div>

On your terminal, the time is green, the module name is cyan, and the level name is bold and has the color of its level: green for `INFO`, red for `ERROR`. That's what the special `<level>` tag does. 🎨

`colorize=True` forces colors on. By default (`colorize=None`), Logust detects whether the stream is a terminal, and honors the `NO_COLOR` and `FORCE_COLOR` environment variables. Files never get colors: there, the tags are simply removed.

### Colors in messages { #colors-in-messages }

You can also use the tags in a message:

```python hl_lines="8-9"
--8<-- "docs_src/formatting/tutorial010.py"
```

<div class="termy">

```console
$ python main.py

INFO     | Deployed version 2.1.0
INFO     | Template: <b>Hello</b>
```

</div>

On a sink with colors, `Deployed` is green and `2.1.0` is bold. On a sink without colors, like a file or a pipe, the tags are removed, so your log files stay clean.

/// note

[JSON sinks](json-output.md) currently keep the tags in the `message` value: `"<green>Deployed</green> version <bold>2.1.0</bold>"`. If you log to JSON, prefer plain messages.

///

### Available tags { #available-tags }

| Tag | Effect |
|-----|--------|
| `<black>`, `<red>`, `<green>`, `<yellow>`, `<blue>`, `<magenta>`, `<cyan>`, `<white>` | Text color |
| `<bright_red>`, `<bright_green>`, ... (also `<light-red>`, `<light-green>`, ...) | Bright text color |
| `<bold>` / `<b>` | Bold |
| `<dim>` | Dimmed |
| `<italic>` / `<i>` | Italic |
| `<underline>` / `<u>` | Underlined |
| `<strike>` / `<s>` | Strikethrough |
| `<level>` | Bold, in the color of the record's level. In formats only |

Tags are case-insensitive. Unknown tags, like `<foo>`, are written as is.

### Markup as plain text { #markup-as-plain-text }

What if your message contains something that *looks* like a tag, like an HTML snippet? Use `logger.opt(colors=False)` for that message, as in the second call of the example above. Its tags are kept as plain text on every sink: `Template: <b>Hello</b>`.

/// note | Technical Details

loguru only parses markup in a message when you use `opt(colors=True)`. Logust always parses it, and `opt(colors=False)` turns that off for one message. `opt(colors=True)` is accepted and behaves like the default.

Exception messages logged by [`logger.catch()`](exceptions.md#the-catch-decorator) are never parsed as markup.

///

## Recap { #recap }

* The default format is `{time} | {level:<8} | {name}:{function}:{line} - {message}`.
* Pass `format=` to `logger.add()` to choose the layout of each sink.
* Tokens cover the time, level, message, caller, thread, process, elapsed time, extra values and the exception.
* `{level:<8}` aligns the level. Every token takes a Python format spec (`{line:05d}`, `{message:>20}`...), with the same output in every sink, and an invalid spec raises `ValueError` in `logger.add()`.
* `{time:<spec>}` takes loguru's time tokens, `!UTC`, or a `strftime` format.
* `{extra[key]}` writes one context value, `{extra}` all of them.
* `{exception}` places the traceback yourself.
* `<red>`, `<bold>`, `<level>`... add colors. They are removed on sinks without colors, and `opt(colors=False)` keeps them as text.

Next, let's see how to get machine-readable logs with [JSON Output](json-output.md).
