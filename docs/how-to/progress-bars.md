# Progress Bars { #progress-bars }

Live displays like <a href="https://rich.readthedocs.io/en/stable/progress.html" class="external-link" target="_blank">`rich.progress`</a> and <a href="https://tqdm.github.io" class="external-link" target="_blank">`tqdm`</a> redraw the progress bar in place, on the last lines of the terminal.

Logust's default console handler writes straight to the process stderr. The progress bar library doesn't know about those lines, so they land in the middle of the bar, and you get a mess of half-drawn bars and log lines. 😱

The fix: replace the default handler with a **callable sink** that prints **through the progress bar's own API**. The library then clears the bar, prints your log line, and redraws the bar below it.

## With rich { #with-rich }

Use `progress.console.print()` as the sink:

```python hl_lines="8 11-15 24"
--8<-- "docs_src/how_to_progress_bars/tutorial001.py"
```

The log lines stay above the bar, and the bar keeps updating at the bottom:

<div class="termy">

```console
$ python main.py

2026-10-06T12:00:43.636146+09:00 | INFO     | Checkpoint 0 reached
2026-10-06T12:00:43.932479+09:00 | INFO     | Checkpoint 25 reached
2026-10-06T12:00:44.226180+09:00 | INFO     | Checkpoint 50 reached
2026-10-06T12:00:44.523119+09:00 | INFO     | Checkpoint 75 reached
Processing ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
```

</div>

Let's see the pieces:

* `logger.remove()` removes the default console handler, so nothing writes to the terminal behind rich's back.
* The sink is added **inside** `with Progress()`, because it needs the `progress` object.
* `colorize=True` gives the line its level colors and renders the `<green>...</green>` [markup](../tutorial/formatting.md#colors-in-messages), as on the console. Callable sinks have no colors by default.
* `Text.from_ansi()` turns the ANSI color codes into a rich `Text`. If you pass the plain string instead, rich parses it as **rich markup**, which mangles the ANSI codes.
* `logger.remove(handler_id)` removes the sink before the display is closed.

/// note

In callable sinks, `{time}` is written in ISO 8601 with microseconds and the UTC offset, as you see above. To get the console look, use an explicit time format, like `{time:YYYY-MM-DD HH:mm:ss.SSS}`. See [Time formatting](../tutorial/formatting.md#time-formatting).

///

There's a longer runnable version of this in <a href="https://github.com/yamaaaaaa31/logust/blob/main/examples/09_rich_progress.py" class="external-link" target="_blank">`examples/09_rich_progress.py`</a>.

## With tqdm { #with-tqdm }

`tqdm.write()` does the same job for tqdm:

```python hl_lines="7-8"
--8<-- "docs_src/how_to_progress_bars/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06T12:00:44.906003+09:00 | INFO     | __main__:<module>:13 - Checkpoint 0 reached
2026-10-06T12:00:45.216906+09:00 | INFO     | __main__:<module>:13 - Checkpoint 25 reached
2026-10-06T12:00:45.530462+09:00 | INFO     | __main__:<module>:13 - Checkpoint 50 reached
2026-10-06T12:00:45.825992+09:00 | INFO     | __main__:<module>:13 - Checkpoint 75 reached
100%|██████████| 100/100 [00:01<00:00, 84.78it/s]
```

</div>

Here the sink is added before the loop: `tqdm.write()` is a class method, so it works with any bar that is active when it is called.

## Don't pass `end=""` { #dont-pass-end }

If you are coming from loguru, you may have recipes like `tqdm.write(msg, end="")`. loguru gives callable sinks the message **with** a trailing newline, so those recipes remove the extra one.

Logust gives callable sinks the message **without** a trailing newline. So, with Logust, `end=""` joins all your log lines into one:

```python hl_lines="6"
--8<-- "docs_src/how_to_progress_bars/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

2026-10-06T12:00:19.704421+09:00 | INFO     | __main__:<module>:9 - Item 0 done2026-10-06T12:00:19.704965+09:00 | INFO     | __main__:<module>:9 - Item 1 done2026-10-06T12:00:19.705008+09:00 | INFO     | __main__:<module>:9 - Item 2 done
```

</div>

Just drop `end=""`, as in the examples above. See [Migrate from loguru](migrate-from-loguru.md#callable-sinks-receive-no-trailing-newline) for the other differences.

## Add the sink after the display starts { #add-the-sink-after-the-display-starts }

A sink is bound when you call `logger.add()`. While a rich display is active, rich swaps `sys.stdout` for a proxy that prints above the bar. That means:

* `logger.add(sys.stdout)` **before** `with Progress()` binds the real stdout, and the two don't cooperate.
* `logger.add(sys.stdout)` **inside** `with Progress()` binds rich's proxy, so it works too.

The callable sink with `progress.console.print()` is the most explicit option, and it works the same way in every case.

## Recap { #recap }

* Remove the default handler with `logger.remove()`, so nothing writes under the bar.
* With rich, add `lambda msg: progress.console.print(Text.from_ansi(msg))` inside `with Progress()`.
* With tqdm, add `lambda msg: tqdm.write(msg)`.
* Pass `colorize=True` to keep level colors and markup.
* Don't use `end=""`: Logust's callable sinks get no trailing newline.
