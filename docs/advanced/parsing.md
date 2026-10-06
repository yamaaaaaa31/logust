# Parsing Log Files { #parsing-log-files }

Logs are not only for reading with your eyes. Sometimes you want to **analyze** them: find the slow requests of the last hour, count errors per user, extract the data for a report...

Logust includes two small helpers to read log files back as Python dicts: `parse()` for text logs, and `parse_json()` for [JSON logs](../tutorial/json-output.md).

## Parse a text log { #parse-a-text-log }

`parse()` takes a file path and a **regular expression** with **named groups**. It reads the file line by line, and gives you a dict with the groups of each line that matches:

```python hl_lines="1 10 12"
--8<-- "docs_src/advanced_parsing/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

{'time': '2026-10-06 12:09:56.309', 'level': 'INFO', 'message': 'Server started'}
{'time': '2026-10-06 12:09:56.309', 'level': 'WARNING', 'message': 'Disk usage is at 91%'}
{'time': '2026-10-06 12:09:56.309', 'level': 'ERROR', 'message': 'Payment failed'}
```

</div>

Each named group, like `(?P<level>\w+)`, becomes a key of the dict.

A few details:

* Lines that **don't match** the pattern are skipped. That's convenient for multi-line messages like tracebacks: only the first line of each record matches.
* The pattern must match from the **start** of the line (it's used with `re.match()`).
* `parse()` is a **generator**: it reads the file lazily, so it works with big files too.
* The file is read as UTF-8, invalid bytes are replaced.

/// tip

Write the pattern for the format you used in `logger.add()`. If you control both, a simple and regular format (like `{time} | {level:<8} | {message}`) makes the pattern easy.

///

## Convert values with cast { #convert-values-with-cast }

All the values are strings by default. Pass `cast` to convert some groups, with a dict of group name to type (or any function that takes a string):

```python hl_lines="14"
--8<-- "docs_src/advanced_parsing/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

[{'level': 'INFO', 'path': '/search', 'status': 200, 'ms': 840}]
```

</div>

`status` and `ms` are `int`s now, so `record["ms"] > 500` works. 🎉

If a conversion fails (a `ValueError` or `TypeError`), the value is kept as a string.

Notice that this example uses `logger.parse()`: it's the same function as `logust.parse()`, available on the logger like in loguru.

/// note | Technical Details

Unlike loguru's `logger.parse()`, Logust's takes a file **path** (not an open file), and `cast` must be a dict. `parse()` also accepts a `chunk_size=` argument, which currently has no effect.

///

## Parse a JSON log { #parse-a-json-log }

If you write your logs with `serialize=True`, there's no need for a pattern. `parse_json()` reads a **JSON Lines** file, one JSON object per line:

```python hl_lines="1 9 12"
--8<-- "docs_src/advanced_parsing/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

INFO Logged in {'user': 'alice'}
ERROR Payment failed {'user': 'bob'}
1 error(s)
```

</div>

Each record is the dict that was serialized, with `time`, `level`, `message`, the caller fields, and `extra`.

By default, lines that are not valid JSON are skipped, and empty lines too. Pass `strict=True` to raise a `ValueError` on the first invalid line instead, with its line number:

```python
for record in parse_json("app.json", strict=True):
    ...
```

## Recap { #recap }

* `parse(path, pattern)` yields a dict of the named groups of each matching line.
* `cast={"ms": int}` converts values.
* `logger.parse()` is the same as `logust.parse()`.
* `parse_json(path)` reads JSON Lines files written with `serialize=True`.
* Both are generators, so they work with large files.
