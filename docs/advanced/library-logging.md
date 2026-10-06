# Logging in Libraries { #logging-in-libraries }

If you write a **library** that other people use, you probably want to log from it too. But your users didn't ask to see your library's messages in their console. A well-behaved library stays **quiet by default**, and lets the application turn its logs on.

Logust does this like loguru: with `logger.disable(name)` and `logger.enable(name)`, per **module**.

## A quiet library { #a-quiet-library }

Let's say your library is a package called `mylib`. In its `__init__.py`, disable its own messages:

```python title="mylib/__init__.py" hl_lines="3"
--8<-- "docs_src/advanced_library_logging/mylib/__init__.py"
```

`logger.disable("mylib")` drops every message logged from the module `mylib`, **and** its submodules (`mylib.api`, `mylib.db`...).

The library logs as usual. It doesn't need anything special for that.

## Turn it on in the application { #turn-it-on-in-the-application }

Now, in the application that uses the library, the messages are hidden until you call `logger.enable("mylib")`:

```python hl_lines="13"
--8<-- "docs_src/advanced_library_logging/tutorial001.py"
```

<div class="termy">

```console
$ python main.py

__main__ | Application starting
mylib | Connecting to the service
```

</div>

The first `mylib.connect()` is silent. After `logger.enable("mylib")`, the second one is logged. 🎉

The application's own messages (`__main__`) were never affected.

## How names are matched { #how-names-are-matched }

The name is compared with the module the message was logged from: its `__name__`, the same value you get in `record["name"]` and `{name}`.

It matches on **dotted boundaries**: `disable("mylib")` covers `mylib` and `mylib.api`, but not `mylibrary`.

### The most specific rule wins { #the-most-specific-rule-wins }

You can combine rules for a package and its submodules. The most specific one wins:

```python hl_lines="11"
--8<-- "docs_src/advanced_library_logging/tutorial002.py"
```

<div class="termy">

```console
$ python main.py

mylib.api | Fetching invoice-7
```

</div>

`mylib` is still disabled (by its own `__init__.py`), but `mylib.api` is enabled, so only the messages from `mylib.api` are shown.

Enabling or disabling a module **replaces** the rules of its submodules. So after this, a call to `logger.enable("mylib")` would enable all of `mylib` again, `mylib.api` included.

### All modules at once { #all-modules-at-once }

The empty string means every module:

```python
logger.disable("")  # Disable every module
logger.enable("")   # Remove every rule
```

## Where the rules apply { #where-the-rules-apply }

The rules are global:

* They are shared by `logger`, by the `logust.enable()` / `logust.disable()` shortcuts, and by every logger made with `bind()` or `patch()`.
* They apply to every logging method: `info()` and friends, `log()`, `exception()`, `opt()` and `catch()`.
* With [`opt(lazy=True)`](opt.md#lazy-evaluation), the lazy arguments of a disabled module are not even evaluated.
* Messages from the standard `logging` module, forwarded with [`InterceptHandler`](../how-to/intercept-standard-logging.md), are matched against the **stdlib logger name**. So `logger.disable("urllib3")` silences urllib3.

You can also set the rules with `logger.configure()`. They are applied in order:

```python
logger.configure(activation=[("mylib", False), ("mylib.api", True)])
```

/// note | Technical Details

While no module is disabled, logging calls skip this check entirely. Once a rule exists, each message looks up its module in a cache, so the cost is one frame lookup and one dictionary lookup.

///

## Level names vs module names { #level-names-vs-module-names }

There's one thing to know: in Logust, `enable()` and `disable()` **without** a name turn the **console** handler on and off (see [Log Levels](../tutorial/log-levels.md)). And `enable()` also accepts a level:

```python
logger.disable()          # Turn the console off
logger.enable()           # Turn it back on
logger.enable("INFO")     # Turn it back on, at INFO
```

So how does Logust know whether `enable("something")` is about a level or a module? It checks the name:

* A **built-in level name** (`trace`, `debug`, `info`, `success`, `warning`, `error`, `fail`, `critical`, in any case) is a **level**.
* **Anything else** is a **module** name.

```python
logger.enable("INFO")   # Re-enable the console at INFO
logger.enable("mylib")  # Enable the mylib module
```

/// warning

A top-level module named like a built-in level (say, a module called `error`) can still be disabled with `disable("error")`. After that, `enable("error")` re-enables the **module**, because a rule with that name exists. Without such a rule, `enable("error")` is about the console. `enable("")` always clears every module rule.

///

## Recap { #recap }

* Libraries call `logger.disable("mylib")` to stay quiet by default.
* Applications call `logger.enable("mylib")` to see the library's messages.
* Names match the module and its submodules, and the most specific rule wins.
* `""` means every module.
* `enable("INFO")` is about the console, `enable("mylib")` is about a module.
