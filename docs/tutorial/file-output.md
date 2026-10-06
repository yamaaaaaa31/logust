# Logging to Files { #logging-to-files }

Console output is great while you develop. In production, you usually want your logs in a **file** too, so you can read them after the fact.

With Logust, a file is just another sink: pass a **path** to `logger.add()`.

## Add a file { #add-a-file }

```python hl_lines="3"
--8<-- "docs_src/file_output/tutorial001.py"
```

Run it, and look at the file it created:

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:04:05.451</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">5</font> - Server starting
<font color="#8A8A8A">2026-10-06 12:04:05.451</font> | <font color="#C4A000"><b>WARNING </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">6</font> - Cache is almost full

$ cat app.log

2026-10-06 12:04:05.451 | INFO     | __main__:&lt;module&gt;:5 - Server starting
2026-10-06 12:04:05.451 | WARNING  | __main__:&lt;module&gt;:6 - Cache is almost full
```

</div>

The default handler is still there, so you get the messages on the console **and** in `app.log`.

The file uses the same default format, without the color codes. Logust writes files as **UTF-8**, and **appends** to the file if it already exists.

The path can be a `str` or a `pathlib.Path`. A relative path is relative to the current working directory.

/// note | Technical Details

The writing is done by the Rust core: formatting the line and writing it to the file happen without going back to Python, which is a big part of why Logust is fast. 🚀

///

## A level per file { #a-level-per-file }

As with any handler, you can choose the minimum `level` of each file. A common setup is a file with everything, plus a file with only the errors:

```python hl_lines="3-5"
--8<-- "docs_src/file_output/tutorial002.py"
```

<div class="termy">

```console
$ python main.py
$ ls logs

app.log
app.log.lock
errors.log
errors.log.lock

$ cat logs/app.log

2026-10-06 12:04:05.656 | INFO     | __main__:&lt;module&gt;:7 - Server starting
2026-10-06 12:04:05.656 | ERROR    | __main__:&lt;module&gt;:8 - Could not send the email

$ cat logs/errors.log

2026-10-06 12:04:05.656 | ERROR    | __main__:&lt;module&gt;:8 - Could not send the email
```

</div>

A few things to notice:

* `logger.remove()` removed the default handler first, so nothing was printed to the console.
* The `logs` directory didn't exist. Logust **created it** for you.
* The `ERROR` message went to both files, the `INFO` message only to `app.log`.

Files you add start at `DEBUG` unless you pass `level`. [`set_level()`](log-levels.md#set-the-minimum-level) only changes the console, never the files.

/// info

Next to each log file, Logust keeps an empty **`.lock`** file (`app.log.lock`). It's used to coordinate writes and rotation when several processes write to the same log file.

You can ignore it, and add `*.log.lock` to your `.gitignore` if your logs live inside a repository.

///

## A format per file { #a-format-per-file }

The `format` argument works with files exactly as with the console:

```python hl_lines="4"
--8<-- "docs_src/file_output/tutorial003.py"
```

<div class="termy">

```console
$ python main.py
$ cat app.log

2026-10-06 12:04:05 INFO Server starting
```

</div>

You'll see all the fields and time tokens in [Formatting](formatting.md). And if your logs are read by a machine more than by a person, [JSON Output](json-output.md) is probably what you want.

## When it's written { #make-sure-its-written }

To be fast, Logust **buffers** file writes: lines are kept in memory (8 KB) and written to the file when the buffer is full. What's left is written when your program exits normally, so usually you don't have to think about it, even if you never call anything.

If you want to read the file from the same program, or make sure the messages are in the file at a specific point, call `logger.complete()`:

```python hl_lines="7"
--8<-- "docs_src/file_output/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06 12:04:05.962 | INFO     | __main__:&lt;module&gt;:6 - Saved to the file
```

</div>

Without `logger.complete()`, the file could still be empty when you open it. `logger.remove()` also writes what the removed handlers hold.

A file with [rotation](rotation-retention.md) is the exception: each line is written when it is logged, so that several processes can share and rotate it.

### When the process is killed { #when-the-process-is-killed }

A normal exit writes the buffer. But a process that ends **without cleanup** loses the lines still in memory: killed by a signal like `SIGTERM` (Docker and Kubernetes send it to stop a container, and Uvicorn re-raises it after a graceful shutdown), stopped with `os._exit()`, or crashed.

If those last lines matter, you have two options:

* `buffering=1` (as in `open()`) writes each line to the file **before the logging call returns**. It survives any of those, and `tail -f app.log` shows the lines right away. That's what loguru and the standard `logging` module do:

    ```python
    logger.add("app.log", buffering=1)
    ```

* Call `logger.complete()` in your shutdown code, before the process can be killed. See [FastAPI](../how-to/fastapi.md#flush-file-logs-on-shutdown) for an example.

Writing every line costs one system call per message, and that's most of the time of a file log call. Here's the time per message for a file sink with the default format, on an Apple Silicon Mac (100,000 messages, best of 7 runs):

| Sink | Time per message | A killed process loses... |
|------|------------------|---------------------------|
| `logger.add("app.log")` | 0.9 µs | up to 8 KB of lines |
| `logger.add("app.log", buffering=1)` | 2.5 µs | nothing |
| `logger.add("app.log", buffering=65536)` | 0.9 µs | up to 64 KiB of lines |
| `logger.add("app.log", enqueue=True)` | 0.9 µs (in the calling thread) | the last ~100 ms of lines |

/// tip

With `buffering=1`, the line is in the operating system's hands when the call returns, which is enough to survive the process dying. Surviving a power loss or a kernel crash would need an `fsync()` per line, which Logust doesn't do (neither do loguru and `logging`).

///

/// note | Technical Details

`buffering` follows `open()`'s rules for a text file: `1` writes each line, a larger number is the buffer size in bytes, and a negative number means the default size of 8192 bytes. `0` (unbuffered) is not allowed for text files in `open()`, and raises `ValueError` here too. Without `buffering`, a file without rotation has an 8 KB buffer, and a rotating file writes each line. A line is never split between two writes, and a line longer than the buffer is written directly.

With `enqueue=True`, `buffering` is ignored: the background thread batches the writes on its own.

///

## Append or overwrite { #append-or-overwrite }

By default, a file is opened in **append** mode (`mode="a"`): every run adds lines at the end, and the old ones stay.

If you want a fresh file on every run, use `mode="w"`:

```python hl_lines="5"
--8<-- "docs_src/file_output/tutorial005.py"
```

Run it twice:

<div class="termy">

```console
$ python main.py
$ python main.py
$ cat history.log

2026-10-06 12:04:06.056 | INFO     | __main__:&lt;module&gt;:7 - Server starting
2026-10-06 12:04:06.127 | INFO     | __main__:&lt;module&gt;:7 - Server starting

$ cat last-run.log

2026-10-06 12:04:06.127 | INFO     | __main__:&lt;module&gt;:7 - Server starting
```

</div>

`history.log` keeps both runs, `last-run.log` only has the last one.

Only `"a"` and `"w"` are supported. Any other mode raises a `ValueError`.

/// note | Technical Details

With `mode="w"`, only the **first** open truncates the file. When Logust reopens it later, for example after [rotation](rotation-retention.md) or in a forked child process, it appends.

///

## Create the file only when needed { #create-the-file-only-when-needed }

A file sink creates its file as soon as you call `add()`, even if nothing is ever logged to it.

For an errors file, that means an empty `errors.log` on every run. With `delay=True`, the file (and its directories) is only created when the **first message** is written:

```python hl_lines="7"
--8<-- "docs_src/file_output/tutorial006.py"
```

<div class="termy">

```console
$ python main.py

errors.log exists? False
errors.log exists? True
```

</div>

/// warning

As the file is opened later, a path that can't be opened (for example, in a directory you don't have permission to write to) is not reported by `add()` anymore. The error happens on the first write, and follows the handler's [`catch` setting](../advanced/sink-errors.md).

///

## Encoding { #encoding }

Files are always written as **UTF-8**, so any text works, emoji and non-Latin scripts included:

```python hl_lines="3"
--8<-- "docs_src/file_output/tutorial007.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:06:22.007</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">5</font> - Café ☕ ログ

$ cat app.log

2026-10-06 12:06:22.007 | INFO     | __main__:&lt;module&gt;:5 - Café ☕ ログ
```

</div>

The `encoding` argument exists for compatibility with loguru. It accepts any spelling of UTF-8 (`"utf-8"`, `"utf8"`, `"UTF-8"`...), and raises a `ValueError` for any other encoding.

/// info

`mode`, `encoding` and `delay` only make sense for files. Passing them to a stream or callable sink raises a `TypeError`, as in loguru.

///

## Writing in the background { #writing-in-the-background }

By default, each logging call writes to the file buffer before it returns. For very high-throughput applications, or when a slow disk must not slow down your code, Logust can do the writing in a background thread with `enqueue=True`:

```python
logger.add("app.log", enqueue=True)
```

That's covered in [Async Writes](../advanced/async-writes.md).

## Recap { #recap }

* `logger.add("app.log")` writes every message to `app.log`, appending to it, in UTF-8. Missing directories are created.
* Each file has its own `level` and `format`. `set_level()` doesn't affect files.
* File writes are buffered. `logger.complete()`, `logger.remove()` and a normal exit write what's pending, even with filters or callable sinks.
* A killed process loses the unwritten lines: use `buffering=1` (one write per line, like loguru) or call `logger.complete()` at shutdown.
* `mode="w"` starts a fresh file on every run, `delay=True` creates the file only when the first message arrives.
* Files grow forever, unless you rotate them. That's the topic of the next chapter: [Rotation, Retention and Compression](rotation-retention.md).
