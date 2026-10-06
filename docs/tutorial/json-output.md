# JSON Output { #json-output }

Text logs are great for humans. But in production, your logs are often read by **machines** first: Elasticsearch, Loki, Datadog, CloudWatch, or a script of your own.

Those tools work best with **structured** logs, where every field has a name and a type. With Logust, that is one option away.

## Use `serialize=True` { #use-serialize-true }

Pass `serialize=True` to `logger.add()` and that sink writes one JSON object per record:

```python hl_lines="6"
--8<-- "docs_src/json_output/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

{"time":"2026-10-06 12:00:42.877","level":"INFO","message":"User logged in","name":"__main__","function":"handle_login","line":10}
{"time":"2026-10-06 12:00:42.877","level":"WARNING","message":"Password expires in 3 days","name":"__main__","function":"<module>","line":14}
```

</div>

That's it. 🎉

Each record is a single line of compact JSON. This format is called **JSON Lines** (or NDJSON), and it's what log shippers expect: they read the stream line by line and parse each line on its own.

## The JSON shape { #the-json-shape }

Here is the first record from above, pretty-printed:

```json
{
  "time": "2026-10-06 12:00:42.877",
  "level": "INFO",
  "message": "User logged in",
  "name": "__main__",
  "function": "handle_login",
  "line": 10
}
```

| Key | Value |
|-----|-------|
| `time` | Local time of the record, with milliseconds |
| `level` | Level name |
| `message` | The message, with its arguments already applied |
| `name` | Module `__name__` of the caller |
| `function` | Caller function |
| `line` | Caller line number, as a number |
| `extra` | The [context values](#json-with-context), only when there are some |
| `exception` | The [traceback](#exceptions-in-json) as a string, only when there is one |

/// info

The JSON shape is fixed: `format=` is ignored when `serialize=True`. If you want a different set of keys, receive the record dict in a [callback](../advanced/callbacks.md) and build the JSON yourself.

///

/// note

`time` has no UTC offset. If your aggregator needs to know the time zone, run the process in UTC (for example with `TZ=UTC`), which is common in containers anyway.

///

## JSON with context { #json-with-context }

JSON really shines when you attach context to your records. Values bound with `bind()` and extra keyword arguments go into an `extra` object:

```python hl_lines="9 12"
--8<-- "docs_src/json_output/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

{"time":"2026-10-06 12:00:42.919","level":"INFO","message":"User action","name":"__main__","function":"<module>","line":10,"extra":{"roles":["admin","billing"],"user_id":123}}
{"time":"2026-10-06 12:00:42.919","level":"INFO","message":"Invoice sent","name":"__main__","function":"<module>","line":12,"extra":{"amount":9.99,"invoice_id":"INV-7","due":"2026-11-01"}}
```

</div>

Notice the types: `user_id` is the number `123`, not the string `"123"`, `roles` is a JSON array, and the `date` became an ISO 8601 string. Your aggregator can filter on `extra.user_id = 123` or sum `extra.amount` without any parsing rules. 🤓

You will learn everything about `bind()` in [Adding Context](context.md).

### How values are converted { #how-values-are-converted }

| Python value | JSON value |
|--------------|------------|
| `None`, `bool`, `str`, `int`, `float` | `null`, boolean, string or number |
| `list`, `tuple`, `set`, `frozenset` | Array |
| `dict` | Object, with the keys converted to strings |
| `bytes`, `bytearray` | UTF-8 string, invalid bytes replaced |
| `datetime`, `date`, `time` | `.isoformat()` string |
| `Enum` | Its `.value`, converted with the same rules |

Anything else, like `Decimal`, `UUID`, `Path` or your own classes, is written as `str(value)`.

/// tip

The conversion only applies to JSON. In a text format, `{extra[user_id]}` still writes `str(value)`.

///

/// note

The order of the keys inside `extra` is not guaranteed and can change between runs. JSON consumers don't care about key order, but don't compare raw lines as strings in your tests: parse them first.

///

## Exceptions in JSON { #exceptions-in-json }

When a record carries an exception, the traceback is added as a string under `exception`:

```python hl_lines="11"
--8<-- "docs_src/json_output/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

{"time":"2026-10-06 12:06:06.993","level":"ERROR","message":"Division failed","name":"__main__","function":"<module>","line":11,"exception":"Traceback (most recent call last):\n  File \"/home/user/project/main.py\", line 9, in <module>\n    result = 1 / 0\n             ~~^~~\nZeroDivisionError: division by zero\n"}
```

</div>

The whole traceback stays inside one JSON line, with its newlines escaped, so a multi-line traceback never gets split into several log entries by your aggregator. You will learn more about logging exceptions in [Logging Exceptions](exceptions.md).

## JSON to stderr for aggregators { #json-to-stderr-for-aggregators }

In a container (Docker, Kubernetes, Cloud Run...), the usual setup is: don't write files at all, write JSON to the standard streams, and let the platform collect them.

```python
import sys

from logust import logger

logger.remove()
logger.add(sys.stderr, serialize=True, level="INFO")
```

`logger.remove()` takes away the default text sink (which writes to stdout), so the only thing your program logs is JSON. Most collectors read both streams of a container, and a text line in the middle would be a parsing error for them.

## Text for you, JSON for machines { #text-for-you-json-for-machines }

Of course, each sink has its own `serialize` option. A common setup is human-readable text on the console and JSON in a file:

```python hl_lines="7-8"
--8<-- "docs_src/json_output/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

12:00:43 | INFO     | Order created
12:00:43 | WARNING  | Payment retried
INFO 1234 Order created
WARNING 1234 Payment retried
```

</div>

The first two lines come from the console sink. The last two come from the end of the program, which reads `app.json` back with nothing more than `json.loads()` on each line.

/// tip

Logust can also read log files back for you, text or JSON, with `parse()` and `parse_json()`. See [Parsing Log Files](../advanced/parsing.md).

///

## Recap { #recap }

* `serialize=True` makes a sink write one compact JSON object per line (JSON Lines).
* Each object has `time`, `level`, `message`, `name`, `function` and `line`, plus `extra` and `exception` when present.
* Context values keep their JSON types: numbers stay numbers, lists become arrays, dates become ISO strings.
* For containers, remove the default sink and write JSON to `sys.stderr`.
* Mix text and JSON sinks freely, each sink chooses its own output.

Next, let's look at how to attach that context: [Adding Context](context.md).
