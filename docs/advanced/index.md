# Advanced User Guide { #advanced-user-guide }

## Additional Features { #additional-features }

The main [Tutorial - User Guide](../tutorial/index.md) should be enough to give you a tour through all the main features of **Logust**.

In the next sections you will see other options, configurations, and additional features.

/// tip

The next sections are **not necessarily "advanced"**.

And it's possible that for your use case, the solution is in one of them.

///

## Read the Tutorial first { #read-the-tutorial-first }

You could still use most of the features in **Logust** with the knowledge from the main [Tutorial - User Guide](../tutorial/index.md).

And the next sections assume you already read it, and that you know those main ideas: levels, message arguments, sinks, files and rotation, formatting, JSON output, context with `bind()` and `contextualize()`, exceptions, and filters.

## What's in this section { #whats-in-this-section }

Each page is independent, so feel free to jump to the one you need:

* [Custom Levels](custom-levels.md): create your own levels, with a color and an icon, and update the built-in ones.
* [Records and patch()](records-and-patch.md): everything a record holds, and how to change records before they are written.
* [Per-message Options with opt()](opt.md): lazy arguments, the current exception, the caller depth, and more, for one message.
* [Callbacks](callbacks.md): react to messages with the full record, for example to send errors to your monitoring.
* [Logging in Libraries](library-logging.md): keep a library quiet by default with `disable("mylib")`, and turn it on with `enable("mylib")`.
* [Tracebacks](tracebacks.md): show the outer frames and the variable values, per handler or per message.
* [Async Writes](async-writes.md): write files from a background thread with `enqueue=True`, and `complete()` at shutdown.
* [Sink Errors](sink-errors.md): decide what happens when a sink fails, with `catch=`.
* [Threads and Processes](threads-and-processes.md): threads, multiprocessing, `fork()`, and free-threaded Python.
* [Performance](performance.md): what makes a log call expensive, and `CollectOptions`.
* [Parsing Log Files](parsing.md): read your logs back as dicts with `parse()` and `parse_json()`.
* [Canonical Events](canonical-events.md): one wide event per request, with tail sampling.

/// info

Looking for recipes, like redirecting the standard `logging` module, setting up FastAPI, or migrating from loguru? Check the [How To - Recipes](../how-to/index.md). 🤓

///
