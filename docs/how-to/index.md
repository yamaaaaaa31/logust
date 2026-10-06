# How To - Recipes { #how-to-recipes }

Here you will find different recipes or "how to" guides for **specific problems**.

Most of these ideas are more or less **independent**, and in most cases you only need to read them if the problem applies directly to **your project**.

If something here looks interesting and useful for your project, go ahead and check it, but otherwise, you can probably just skip them.

/// tip

If you want to **learn Logust** in a structured way (recommended), go and read the [Tutorial - User Guide](../tutorial/index.md) chapter by chapter instead.

///

## The recipes { #the-recipes }

* [Intercept Standard Logging](intercept-standard-logging.md): send everything logged with the standard `logging` module, including the logs of third-party libraries, through Logust.
* [FastAPI and Starlette](fastapi.md): log every request with timing and request IDs, mask sensitive data, or emit one canonical event per request.
* [Function Timing Decorators](timing-decorators.md): log how long a function takes with `@log_fn` and `@debug_fn`.
* [Progress Bars](progress-bars.md): log above a `rich` or `tqdm` progress bar without breaking it.
* [Migrate from loguru](migrate-from-loguru.md): what changes, and what doesn't, when you swap `loguru` for Logust.
* [Migrate from logging](migrate-from-logging.md): how the standard `logging` concepts map to Logust.

## Optional dependencies { #optional-dependencies }

The helpers in `logust.contrib` that these recipes use don't need anything beyond Logust itself, except the FastAPI / Starlette middleware. For it, install one of the extras:

//// tab | FastAPI

<div class="termy">

```console
$ pip install "logust[fastapi]"

---> 100%
```

</div>

////

//// tab | Starlette

<div class="termy">

```console
$ pip install "logust[starlette]"

---> 100%
```

</div>

////

The progress bar recipe uses `rich` or `tqdm`, which you install as usual if you don't have them already.
