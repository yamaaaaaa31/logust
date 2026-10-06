---
hide:
  - navigation
---

# Logust { #logust .logust-home-title }

<div class="logust-hero" markdown>

![Logust](assets/logo.svg)

<p class="logust-tagline"><em>Logust: fast, Rust-powered Python logging, with the loguru API you already know.</em></p>

<p class="logust-badges">
<a href="https://github.com/yamaaaaaa31/logust/actions/workflows/test.yml"><img src="https://github.com/yamaaaaaa31/logust/actions/workflows/test.yml/badge.svg" alt="CI"></a>
<a href="https://pypi.org/project/logust/"><img src="https://badge.fury.io/py/logust.svg" alt="PyPI version"></a>
<a href="https://pypi.org/project/logust/"><img src="https://img.shields.io/pypi/pyversions/logust.svg" alt="Supported Python versions"></a>
<a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

</div>

---

**Documentation**: <a href="https://yamaaaaaa31.github.io/logust/" target="_blank">https://yamaaaaaa31.github.io/logust/</a>

**Source Code**: <a href="https://github.com/yamaaaaaa31/logust" target="_blank">https://github.com/yamaaaaaa31/logust</a>

---

Logust is a logging library for Python. Its API follows <a href="https://github.com/Delgan/loguru" class="external-link" target="_blank">loguru</a>, and the hot path (formatting, serialization and file I/O) is written in Rust.

The key features are:

* **Fast**: Rust core for formatting, JSON serialization and file writes. Tens of times faster than `logging` and `loguru`. [See the benchmarks](about/benchmarks.md).
* **Zero config**: one import and you get colored output with time, level and caller info.
* **Familiar**: the loguru API (`logger.add()`, `bind()`, `catch()`, `opt()`...). Migrating is mostly changing the import.
* **Files done right**: size and time based rotation, retention and compression, with optional background writes.
* **Structured**: JSON output with `serialize=True`, and context with `bind()` and `contextualize()`.
* **Production ready**: exception capture with rich tracebacks, standard `logging` interception, FastAPI / Starlette middleware and canonical request events with tail sampling.

## Requirements { #requirements }

Python 3.10+, on Linux, macOS or Windows. Pre-built wheels are published for all of them, so you don't need a Rust toolchain.

## Installation { #installation }

<div class="termy">

```console
$ pip install logust

---> 100%

Successfully installed logust
```

</div>

## Example { #example }

### Create it { #create-it }

Create a file `main.py` with:

```python
--8<-- "docs_src/index/tutorial001.py"
```

### Run it { #run-it }

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 11:56:11.907</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">3</font> - Hello, Logust!
<font color="#8A8A8A">2026-10-06 11:56:11.908</font> | <font color="#8AE234"><b>SUCCESS </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">4</font> - Connected to the database
<font color="#8A8A8A">2026-10-06 11:56:11.908</font> | <font color="#C4A000"><b>WARNING </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">5</font> - Disk usage is at 91%
<font color="#8A8A8A">2026-10-06 11:56:11.908</font> | <font color="#CC0000"><b>ERROR   </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">6</font> - Payment failed
```

</div>

You didn't configure anything, and you already have:

* A timestamp with milliseconds.
* A colored, aligned **level**.
* The **module**, **function** and **line** that logged the message.
* loguru-style `{}` formatting for message arguments.
* Context attached with `bind()`, ready to show up in your format or in JSON output.

### Example upgrade { #example-upgrade }

Now let's take it to production. Add a file sink that rotates at 500 MB, keeps 30 days of logs, compresses old files, writes JSON, and does the writing in a background thread:

```python hl_lines="3-11"
--8<-- "docs_src/index/tutorial002.py"
```

Every line in `app.log` is now a JSON object:

```json
{"time":"2026-10-06 11:56:11.944","level":"INFO","message":"User logged in","name":"__main__","function":"<module>","line":13,"extra":{"user_id":42}}
```

### Recap { #recap }

In summary, you `import` the logger and log. That's it. 🎉

When you need more, everything is a keyword argument on `logger.add()`: the **level**, the **format**, **rotation**, **retention**, **compression**, **serialize** for JSON, **enqueue** for background writes, **filter**, and more.

For a more complete example including more features, see the [Tutorial - User Guide](tutorial/index.md).

**Spoiler alert**: the tutorial - user guide includes:

* Log **levels**, and how to choose the minimum level.
* Message **arguments** with `{}` placeholders.
* **Handlers** and **sinks**: console, files and any Python callable.
* Log **rotation**, **retention** and **compression**.
* Custom **formats** with color markup.
* **JSON** output for log aggregators.
* **Context** with `bind()` and `contextualize()`.
* Logging **exceptions** with full tracebacks, and the `@logger.catch()` decorator.
* **Filters** per handler.

## Performance { #performance }

Writing 10,000 messages to a file (release build, lower is better):

| Scenario | logging | loguru | logust |
|----------|---------|--------|--------|
| File write (sync) | 963.57 ms | 2676.74 ms | **15.93 ms** |
| Formatted messages | 966.38 ms | 2710.67 ms | **15.65 ms** |
| JSON serialize | N/A | 2717.99 ms | **14.91 ms** |
| With context (sync) | N/A | 2600.08 ms | **14.29 ms** |
| File write (async + complete) | N/A | 3019.49 ms | **16.50 ms** |

To learn more about it, see the section [Benchmarks](about/benchmarks.md).

## Optional Dependencies { #optional-dependencies }

Logust has no required dependencies. Some integrations are installed with extras:

* `logust[fastapi]`: the request logging middleware for <a href="https://fastapi.tiangolo.com/" class="external-link" target="_blank">FastAPI</a>.
* `logust[starlette]`: the same middleware for plain <a href="https://www.starlette.io/" class="external-link" target="_blank">Starlette</a>.

## License { #license }

This project is licensed under the terms of the MIT license.
