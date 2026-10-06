# Message Arguments { #message-arguments }

Most log messages include some data: a user name, a count, a duration. You could build the string yourself with an f-string, but Logust gives you a better way: pass the values as **arguments** and let Logust put them in the message.

## Positional arguments { #positional-arguments }

Write `{}` where a value should go, and pass the values after the message:

```python hl_lines="3-4"
--8<-- "docs_src/message_arguments/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:07.316</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">3</font> - Processed 42 items in 1.5 seconds
<font color="#8A8A8A">2026-10-06 12:01:07.316</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">4</font> - Hello, world!
```

</div>

If this looks familiar, it's because it is: the message is formatted with Python's own [`str.format()`](https://docs.python.org/3/library/string.html#formatstrings). The `{}` placeholders are filled in order, and `{0}`, `{1}`... pick an argument by position.

## Keyword arguments { #keyword-arguments }

You can also give the placeholders a name and pass the values as keyword arguments:

```python hl_lines="3-4"
--8<-- "docs_src/message_arguments/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:07.373</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">3</font> - User alice logged in from 10.0.0.1
<font color="#8A8A8A">2026-10-06 12:01:07.373</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">4</font> - login by alice
```

</div>

Named placeholders make longer messages easier to read, and you can mix them with positional ones, as in the second call.

## Format specifications { #format-specifications }

As this is `str.format()`, everything you know from it works: format specs after a `:`, conversions like `!r`, attribute access like `{user.name}` and item access like `{data[key]}`:

```python hl_lines="3-6"
--8<-- "docs_src/message_arguments/tutorial003.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:07.432</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">3</font> - Progress: 45.7%
<font color="#8A8A8A">2026-10-06 12:01:07.432</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">4</font> - Price:     9.50 EUR
<font color="#8A8A8A">2026-10-06 12:01:07.432</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">5</font> - Raw value: 'text'
<font color="#8A8A8A">2026-10-06 12:01:07.432</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">6</font> - Total: 1,234,567
```

</div>

## Extra keyword arguments go to `extra` { #extra-keyword-arguments-go-to-extra }

What happens if you pass a keyword argument that is **not** used in the message?

It is not lost. It's stored in the record's **`extra`** dictionary, the place where Logust keeps contextual data about a message.

To see it, this example replaces the default handler with one whose format shows `{extra}`. Don't worry about `remove()` and `add()` yet, they are the topic of the [next chapter](sinks.md):

```python hl_lines="6 8-9"
--8<-- "docs_src/message_arguments/tutorial004.py"
```

<div class="termy">

```console
$ python main.py

<font color="#4E9A06"><b>INFO    </b></font> | Order 1234 paid | {'amount': 9.99, 'currency': 'EUR'}
<font color="#4E9A06"><b>INFO    </b></font> | Cache cleared | {'keys': 128}
```

</div>

Check it:

* `order_id` is used by the `{order_id}` placeholder, so it goes into the message.
* `amount` and `currency` are not in the message, so they end up in `extra`.
* `keys` too: a message doesn't need any placeholder to carry extra data.

This is really useful with [JSON output](json-output.md), where `extra` becomes a JSON object that your log platform can search and filter. 🤓

/// note | Difference from loguru

loguru copies **every** keyword argument into `extra`, including the ones used in the message. Logust only keeps the ones that no placeholder used, so in the example above `order_id` is not in `extra`.

If you want a value both in the message and in `extra`, attach it with `bind()`, as you will see in [Context](context.md).

///

## Braces in messages { #braces-in-messages }

A message is only formatted when you pass arguments. Without arguments, braces are kept exactly as they are, so logging a string that happens to contain `{` and `}` is always safe:

```python hl_lines="3-4"
--8<-- "docs_src/message_arguments/tutorial005.py"
```

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:07.547</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">3</font> - Without arguments, {braces} stay as they are: {}
<font color="#8A8A8A">2026-10-06 12:01:07.547</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">4</font> - With arguments, double them: {literal} and a value
```

</div>

When you do pass arguments, the usual `str.format()` rule applies: write `{{` and `}}` to get a literal `{` and `}`.

/// warning

When the message is formatted, a placeholder without a matching argument raises an error from the logging call, just like `str.format()` would:

```python
--8<-- "docs_src/message_arguments/tutorial007.py"
```

<div class="termy">

```console
$ python main.py

IndexError: Replacement index 1 out of range for positional args tuple
KeyError: 'name'
```

</div>

///

## Why not f-strings? { #why-not-f-strings }

You can use f-strings with Logust, they work fine. But arguments have one big advantage: they are **lazy**.

An f-string is built by Python **before** Logust is even called, so the work is done even when the message is filtered out. With arguments, Logust first checks the level, and only formats the message if some handler is going to use it.

Let's see it with an object that announces when it gets formatted:

```python hl_lines="12-14"
--8<-- "docs_src/message_arguments/tutorial006.py"
```

<div class="termy">

```console
$ python main.py

  ...formatting the report...
  ...formatting the report...
<font color="#8A8A8A">2026-10-06 12:01:07.604</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">14</font> - arguments: REPORT
```

</div>

The level is `INFO`, so both `debug()` calls are dropped. But:

* The **f-string** was formatted anyway (the first "formatting" line), for a message nobody sees.
* The `debug()` call **with arguments** never formatted the report.
* The `info()` call with arguments formatted it, because that message is shown (the second "formatting" line).

For a single message this doesn't matter. In a hot loop that logs at `DEBUG` in production, it adds up.

/// tip

Arguments are lazy about **formatting**, but Python still evaluates the argument expressions themselves (`Report()` above was created three times). If computing a value is expensive, guard it with [`is_level_enabled()`](log-levels.md#skip-expensive-work), or use [`opt(lazy=True)`](../advanced/opt.md) to pass a function that is only called when needed.

///

## Recap { #recap }

* Use `{}` placeholders and pass values as positional arguments: `logger.info("Took {} ms", 42)`.
* Use `{name}` placeholders with keyword arguments: `logger.info("Hi {user}", user="alice")`.
* All of `str.format()` works: format specs, `!r`, attributes and items.
* Keyword arguments not used in the message are stored in `extra`.
* Without arguments, braces are left alone. With arguments, write `{{` and `}}` for literal braces.
* Arguments are only formatted when the message is going to be logged, f-strings always are.
