# Rotation, Retention and Compression { #rotation-retention-and-compression }

The log file you created in [Logging to Files](file-output.md) has a problem: it grows forever. Sooner or later, it fills up the disk. 💥

The solution has three parts, each one an argument of `logger.add()`:

* **Rotation**: when a file gets too big or too old, close it and start a new one.
* **Retention**: delete old rotated files.
* **Compression**: compress rotated files to save space.

## Rotate by size { #rotate-by-size }

Let's rotate the file when it reaches 1 KB. That's way too small for a real application, but it lets you see it happen right away:

```python hl_lines="4"
--8<-- "docs_src/rotation_retention/tutorial001.py"
```

<div class="termy">

```console
$ python main.py
$ ls logs

app.2026-10-06_12-04-43_952663.pid60264.log
app.2026-10-06_12-04-43_953057.pid60264.log
app.log
app.log.lock

$ head -n 1 logs/app.log

2026-10-06 12:04:43.953 | INFO     | __main__:&lt;module&gt;:7 - Processing item 28
```

</div>

Forty messages didn't fit in 1 KB, so the file was rotated twice:

* When `app.log` reached the size limit, Logust **renamed** it, adding the date and time of the rotation to the name.
* Then it started a new, empty `app.log` and kept writing there.

So `app.log` is always the **current** file, the one with the latest messages (here, from item 28 on).

The check is done before each write: once the file has reached the limit, the next message goes to a new file. A rotated file can be a bit larger than the limit, by at most one message.

### Rotated file names { #rotated-file-names }

A rotated file is named like this:

```
app.2026-10-06_12-04-43_952663.pid60264.log
```

* `app`: the name of your file, without the extension.
* `2026-10-06_12-04-43_952663`: the local date and time **of the rotation**, down to the microsecond.
* `pid60264`: the ID of the process that rotated it.
* `.log`: the original extension.

The microseconds and the process ID make sure two rotations never pick the same name, even when several processes share the same log file. As the names start with the date, sorting them alphabetically also sorts them by time.

### Size units { #size-units }

A size is a number followed by a unit, with or without a space, in upper or lower case:

```python hl_lines="4-6"
--8<-- "docs_src/rotation_retention/tutorial002.py"
```

| Unit | Meaning |
|------|---------|
| `B` (or no unit) | bytes |
| `K`, `KB` | 1024 bytes |
| `M`, `MB` | 1024 × 1024 bytes |
| `G`, `GB` | 1024 × 1024 × 1024 bytes |
| `T`, `TB` | 1024⁴ bytes |

Decimals work too, like `"1.5 GB"`.

## Rotate by time { #rotate-by-time }

You can also start a new file every day or every hour:

```python hl_lines="6-7"
--8<-- "docs_src/rotation_retention/tutorial003.py"
```

* `"daily"` (also `"1 day"`) rotates at **midnight**, local time.
* `"hourly"` (also `"1 hour"`) rotates at the start of every hour.

Rotation is aligned to the clock, not to when the file was opened: a file opened at 23:50 with `"daily"` is rotated at midnight, ten minutes later.

The rotation happens with the first message written after the boundary. If your application was stopped overnight, `app.log` still has yesterday's messages, and it's rotated as soon as you log the first message of the new day.

That also works for short-lived processes, like a script run by `cron` every few minutes: when a run opens an `app.log` that was last written before the current boundary (an earlier day, or an earlier hour), the first message rotates it. So you still get one file per day or per hour.

### Daylight saving time { #daylight-saving-time }

Boundaries are **local wall-clock** times, so they follow daylight saving changes, the same way as in loguru. Most of the time you don't need to think about it, but if you are curious:

/// details | Technical Details

* When clocks **fall back** and an hour repeats, the file rotates at the **first** occurrence of the boundary. The repeated hour doesn't rotate again: with `"hourly"`, the file started at 01:00 covers both 01:00 hours, and the next rotation is at 02:00.
* When clocks **spring forward** and the boundary falls into the skipped hour, the file rotates at the transition itself, the first instant after the gap. For example, a `"daily"` file in a zone that skips midnight, like `America/Santiago`, rotates when the clock jumps to 01:00.
* The next boundary is computed when a file is opened or rotated, never for each message, so this costs nothing on your logging calls.

///

### `timedelta` and `time` { #timedelta-and-time }

For compatibility with loguru, `rotation` also accepts `datetime.timedelta` and `datetime.time` values, as long as they mean the same as `"daily"` or `"hourly"`:

```python hl_lines="9-11"
--8<-- "docs_src/rotation_retention/tutorial003.py"
```

| Value | Same as |
|-------|---------|
| `timedelta(days=1)` | `"daily"` |
| `timedelta(hours=1)` | `"hourly"` |
| `time(0, 0)` | `"daily"` |

Any other interval or time of day raises a `ValueError` when you call `logger.add()`, instead of silently doing something different from what you asked for:

```python hl_lines="6"
--8<-- "docs_src/rotation_retention/tutorial008.py"
```

<div class="termy">

```console
$ python main.py

ValueError: Unsupported rotation interval datetime.timedelta(days=7): only timedelta(days=1) (daily, at midnight) and timedelta(hours=1) (hourly, on the hour) are supported
ValueError: compression format 'xz' is not supported by logust (no LZMA encoder is bundled); supported formats: gz, bz2, zip, tar, tar.gz, tar.bz2
```

</div>

(The second error is about compression, you will see it [below](#compression).)

### All rotation values { #all-rotation-values }

To sum up, these are the values `rotation` accepts:

| Value | Rotates |
|-------|---------|
| `"500 MB"`, `"1.5 GB"`, `"100 KB"`, ... | When the file reaches that size |
| `"daily"`, `"1 day"`, `timedelta(days=1)`, `time(0, 0)` | Every day at midnight |
| `"hourly"`, `"1 hour"`, `timedelta(hours=1)` | Every hour, on the hour |
| `None` (default) | Never |

Any other value is rejected right away, when you call `logger.add()`: an unsupported string, like `"1 week"`, `"10 seconds"` or `"midnight"`, raises a `ValueError`, and a value of another type, like an `int`, raises a `TypeError`:

```python hl_lines="5"
--8<-- "docs_src/rotation_retention/tutorial009.py"
```

<div class="termy">

```console
$ python main.py

ValueError: Unsupported rotation "1 week": use "daily", "hourly" or a size such as "500 MB"
ValueError: Unsupported rotation "midnight": use "daily", "hourly" or a size such as "500 MB"
TypeError: rotation must be str, datetime.timedelta or datetime.time, not int
```

</div>

That's on purpose: a typo in `rotation` should fail when your application starts, not leave you with one huge file that is never rotated. 🚨

/// info

loguru accepts more rotation values, like `"1 week"`, `"monday at 12:00"` or a custom function. Logust supports the most common ones, which can be checked very cheaply on every write.

///

## Retention { #retention }

Rotation alone doesn't save any space: it just splits the logs into several files. To delete old files, add **retention**.

### Keep a number of files { #keep-a-number-of-files }

Pass an `int` to keep only that many rotated files:

```python hl_lines="4"
--8<-- "docs_src/rotation_retention/tutorial004.py"
```

<div class="termy">

```console
$ python main.py
$ ls logs

app.2026-10-06_12-04-44_032873.pid60269.log
app.2026-10-06_12-04-44_033240.pid60269.log
app.2026-10-06_12-04-44_033612.pid60269.log
app.log
app.log.lock
```

</div>

A hundred messages produced more rotations than that, but only the **3 most recent** rotated files are kept, plus the current `app.log`, which is never deleted.

### Keep files for some days { #keep-files-for-some-days }

Pass a string like `"10 days"` to delete the rotated files that were last modified more than 10 days ago:

```python hl_lines="4"
--8<-- "docs_src/rotation_retention/tutorial005.py"
```

Retention by time is counted in whole days: `"1 day"`, `"7 days"`, `"30 days"`...

As with rotation, any other retention string, like `"1 week"`, `"2 months"` or `"1 hour"`, raises a `ValueError` when you call `logger.add()`:

```python hl_lines="4"
--8<-- "docs_src/rotation_retention/tutorial010.py"
```

<div class="termy">

```console
$ python main.py

ValueError: Unsupported retention "1 week": use a number of files such as 10 or a duration such as "10 days"
```

</div>

Write `"7 days"` instead of `"1 week"`.

### When retention runs { #when-retention-runs }

Retention is applied **every time a file is rotated**, right after the rotation. That means:

* Without `rotation`, `retention` does nothing, as there are no rotated files to clean up.
* Only files that look like rotated versions of **this** log file are considered (`app.<date>.pid<id>.log`, compressed or not). Other files in the same directory are never touched.

## Compression { #compression }

Rotated files are rarely read, so you can compress them. Pass `compression`:

```python hl_lines="4"
--8<-- "docs_src/rotation_retention/tutorial006.py"
```

<div class="termy">

```console
$ python main.py
$ ls logs

app.2026-10-06_12-04-44_109544.pid60272.log.zip
app.2026-10-06_12-04-44_110303.pid60272.log.zip
app.2026-10-06_12-04-44_110853.pid60272.log.zip
app.log
app.log.lock
```

</div>

Each rotated file is now a `.zip` archive. The current `app.log` is never compressed, so you can keep reading it with `tail -f`.

These are the formats you can choose, with the same names as loguru:

| Value | Archive |
|-------|---------|
| `True`, `"gz"` | gzip (`.log.gz`) |
| `"bz2"` | bzip2 (`.log.bz2`) |
| `"zip"` | ZIP (`.log.zip`) |
| `"tar"` | uncompressed tarball (`.log.tar`) |
| `"tar.gz"` | gzip-compressed tarball (`.log.tar.gz`) |
| `"tar.bz2"` | bzip2-compressed tarball (`.log.tar.bz2`) |
| `False` (default) | No compression |

Archives hold the rotated file under its own name, so `gunzip`, `unzip`, `tar` and Python's `gzip`, `zipfile` or `tarfile` give you back the original file.

Some details:

* `"xz"`, `"lzma"` and `"tar.xz"` raise a `ValueError`: Logust doesn't bundle an LZMA encoder. Any other unknown format raises a `ValueError` too.
* loguru also accepts a function as `compression`. Logust doesn't, and raises a `TypeError`.
* Compression only runs when a file is rotated, so it doesn't slow down your logging calls.
* Retention recognizes rotated files in every format, so if you change `compression` between runs, older archives are still cleaned up.

## All together { #all-together }

A good starting point for a production application looks like this:

```python hl_lines="3-9"
--8<-- "docs_src/rotation_retention/tutorial007.py"
```

* `rotation="500 MB"`: no single file gets bigger than about 500 MB.
* `retention="30 days"`: rotated files older than a month are deleted.
* `compression=True`: rotated files are gzipped.

With this, your logs take a bounded amount of disk space, and you don't have to think about them again. 🎉

/// tip

`rotation`, `retention` and `compression` only apply to **file** sinks. Streams and callables don't have files to rotate.

///

## Recap { #recap }

* `rotation="500 MB"` rotates by size, `rotation="daily"` or `"hourly"` by time, aligned to the clock.
* Rotated files are renamed to `name.<date>_<time>_<microseconds>.pid<id>.ext`, and `app.log` stays the current file.
* `retention=5` keeps the 5 most recent rotated files, `retention="10 days"` deletes the ones older than 10 days. It runs after each rotation.
* `compression=True` gzips rotated files. `"zip"`, `"bz2"`, `"tar"`, `"tar.gz"` and `"tar.bz2"` pick another format.
* Time rotation follows local wall-clock time, daylight saving changes included, and a file left over from an earlier period is rotated on the first write.
* Unsupported rotation and retention values raise a `ValueError` (or a `TypeError` for a wrong type) when you call `logger.add()`.
