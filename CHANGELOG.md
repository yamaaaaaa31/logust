# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`buffering=` for file sinks**: the `open()` argument loguru passes through. `buffering=1` writes each line to the file before the logging call returns (one `write()` per message, as loguru and `logging.FileHandler` do), so logged lines are visible to `tail -f` right away and survive a process killed by `SIGTERM` (Uvicorn re-raises it after a graceful shutdown), stopped with `os._exit()`, or crashed; no `fsync()` is done. `buffering=N` sets the buffer size in bytes, and a negative value means 8192, as in `open()`. The default is unchanged: an 8 KB buffer for sinks without rotation, one write per line for sinks with rotation. `buffering=0` raises `ValueError` (`open()` rejects unbuffered text files), a non-`int` raises `TypeError`, and passing it to a stream or callable sink raises `TypeError` like `mode` and `encoding`. It is ignored with `enqueue=True`, whose writer thread batches on its own. Accepted by `configure(handlers=[...])` and `HandlerConfig`. Per message with the default format: about 0.9 µs by default, 2.5 µs with `buffering=1` (`bench_throughput.py`, 10,000 messages: 29.8 ms, against 89.4 ms for loguru and 83.4 ms for `logging`).
- **`logger.catch()` matches loguru's call shapes**: use it without parentheses (`@logger.catch`) or as a context manager (`with logger.catch():`). New `onerror`, `exclude`, and `default` options; `level` accepts custom level names and numbers. Coroutine and generator functions are decorated correctly.
- **`logger.level()` lookups and updates**: `logger.level("INFO")` returns a `Level(name, no, color, icon)` named tuple, and `logger.level("INFO", color="blue")` (no `no`) updates an existing level, including the console color of built-in levels. Unknown names raise `ValueError`. `Level` is exported from `logust`.
- **`datetime` rotation values**: `add(rotation=...)` accepts `timedelta(days=1)`, `timedelta(hours=1)`, and `time(0, 0)`. Values that can't be honored exactly raise `ValueError`.
- **`logger.parse()`**: the module-level `parse()` is also available on the logger, as in loguru.
- **Positional message arguments**: `logger.info("Processed {} items", 42)` now works like loguru on every level method, `log()`, `exception()`, `opt()`, and the module-level functions (`logust.info(...)`). Positional and keyword arguments can be mixed, kwargs not used by a placeholder still go to `extra`, and a message logged without arguments is never formatted. Filtered-out calls now return before any argument handling, making them about 30% faster than in 0.5.0.
- **loguru format fields**: `{level.name}`, `{level.no}`, `{level.icon}`, `{thread.name}`, `{thread.id}`, `{process.name}`, `{process.id}`, `{file.name}`, and `{file.path}` work in format strings on every sink type, and the caller, thread, and process info they need is collected automatically. Built-in levels get loguru's default icons (`FAIL`, which loguru lacks, gets `✖️`).
- **`{exception}` in format strings**: the traceback is written where `{exception}` stands and is no longer appended after the message, so it is printed once. It is empty for records without an exception.
- **More `compression` formats**: file sinks accept loguru's format strings `"gz"`, `"bz2"`, `"zip"`, `"tar"`, `"tar.gz"` and `"tar.bz2"`, and rotated files get the matching extension (for example `app.<timestamp>.pid<pid>.log.zip`). `compression=True` still means gzip. `"xz"`, `"lzma"` and `"tar.xz"` raise `ValueError`. Retention removes rotated archives in every supported format. Compression still only runs at rotation, so writes are not affected
- **`mode=` for file sinks**: `"a"` (default) appends and `"w"` truncates the file when the sink first opens it
- **`delay=True` for file sinks**: the file and its parent directories are created when the first message is written, so a sink that never logs leaves nothing on disk
- **`encoding=` for file sinks**: accepted for loguru compatibility. Files are always written as UTF-8, so UTF-8 aliases are accepted and other encodings raise `ValueError`
- **`catch=` for every sink type**: `True` prints a loguru-style report to stderr when a sink fails, and `False` raises the error from the logging call (`OSError` for file sinks). The default `None` keeps the previous silent behavior; loguru's default is `catch=True`. Console sinks (`sys.stdout`, `sys.stderr` and the default handler) follow the same policy, with `False` raising `BrokenPipeError` when the reader of a pipe has gone away. `enqueue=True` file sinks are not covered yet: the background writer of an `enqueue=True` sink reports write errors to stderr whatever `catch` is.
- `mode`, `encoding` and `delay` raise `TypeError` for stream and callable sinks, as in loguru. All five options also work in `configure(handlers=[...])`
- **Per-module `enable(name)` / `disable(name)`**: `logger.disable("mylib")` drops messages logged from `mylib` and its submodules, and `logger.enable("mylib")` turns them back on, with loguru's rules (dotted prefix match, most specific rule wins, `""` means all modules). Rules are shared by bound and patched loggers, apply to `log()`, `exception()`, `opt()` and `catch()`, are available as `logust.enable()` / `logust.disable()` and `configure(activation=[...])`, and match the stdlib logger name for records forwarded by `InterceptHandler`. `enable()` / `disable()` without a name and `enable("INFO")` (any built-in level name) still toggle the console, unless `disable(name)` left a rule for a module of that name (`disable("info")` is undone by `enable("info")`). Logging cost is unchanged while no module is disabled
- **`backtrace=` and `diagnose=` per handler**: `add()` and `configure(handlers=[...])` accept loguru's options for tracebacks logged by `exception()`, `catch()` and `opt(exception=True)`. Each handler gets its own variant, and each variant is formatted once per logged exception. Both default to `False`, unlike loguru, because `diagnose` writes variable values into the logs. `opt(backtrace=, diagnose=)` still applies to every handler for one message. Messages without an exception are not affected.
- **`{extra}` format token**: writes the whole extra dict as loguru does (`{'user': 'alice', 'attempt': 2}`), on every sink type. Strings are quoted like `repr()`; keys are sorted, and types other than `str`, numbers, `bool`, `None`, lists, tuples and dicts use `str()`.
- **`opt(colors=False)`**: keeps color markup in that message as plain text on every sink. Message markup is still parsed by default, so `opt(colors=True)` changes nothing (loguru only parses message markup with `colors=True`).
- **`opt(capture=False)`**: keyword arguments only format the message and are not added to `extra`, as in loguru.
- **loguru-shaped record dicts**: filters, patchers, and `add_callback()` callbacks can use loguru's record fields: `record["level"].no` / `.name` / `.icon`, `record["time"]` (an aware `datetime`), `record["elapsed"]` (a `timedelta`), `record["file"].name` / `.path`, `record["thread"].id` / `.name`, `record["process"].id` / `.name`, and `record["module"]`. `record["level"]` and `record["file"]` are `str` subclasses, so `record["level"] == "INFO"` keeps working, and the flat keys (`level_no`, `timestamp`, `thread_id`, ...) stay. The value types (`RecordLevelStr`, `RecordFile`, `RecordThread`, `RecordProcess`, `RecordElapsed`) are exported from `logust`. Logging without a filter, patcher, or callback is unaffected; a filter that runs on every message costs about 0.1 µs more per message

### Changed
- **Cheaper records in the Rust core**: each record reads the system clock once instead of twice (the local UTC offset is reused within the same second and still follows `TZ` and `/etc/localtime` changes within a second, as before), records below every sink's level return before taking any lock and the callback list is only locked when a callback can take the record, custom levels share one registered `LevelInfo` instead of copying its name, color and icon per record, and the default `{time}` digits skip a redundant UTF-8 check. Per message, directly on the Rust logger: file sink with `{message}` 146 → 124 ns (-15%), bound logger -17%, default format with caller info -12%, `enqueue=True` -14%, custom level -25%, callable sink `{message}` -8%, `serialize=True` -7%, filtered-out call -7%. Output is unchanged.
- **Faster callable sinks, filters and callbacks**: callable sink templates are compiled once into a single rendering function, formatted sinks at custom levels and `serialize=True` sinks get only the record fields they use, and the loguru-shaped record values are cheaper to look up. Per message, a callable sink with the default format is about 33% faster, with `{message}` 20%, with a rich format (`{time:...}`, `{level.icon}`, `{thread}`, `{extra}`) 37%, a custom level to a callable sink 39%, a `serialize=True` callable sink 9%, a callable sink with a filter 14–29%, and file sink filters, patchers and `add_callback()` callbacks 3–11%. Output is unchanged.
- **Plain calls cross into Rust once**: `logger.info("msg")` (and the other level methods, `log("INFO", ...)`, bound loggers and `logust.info(...)`) with no arguments, exception, patcher or module rule now hands the message to Rust, which collects the caller frame, thread and process itself from the handlers' needs instead of the Python wrapper reading `sys._getframe` and passing keyword arguments. Measured per call with a file sink (median of alternating runs, noise 1–2%): `{message}` 0.38 → 0.26 µs, default format 0.74 → 0.57 µs, `{name}:{function}:{line}` 0.67 → 0.49 µs, `{thread.name}:{process.name}` 0.75 → 0.47 µs, `log("INFO", ...)` 0.49 → 0.34 µs, `serialize=True` 0.84 → 0.72 µs, callable sinks 1.2–1.3x. Records are identical; calls with arguments, `exception=`, a patcher, a disabled module or a fixed `CallerInfo` keep the Python path and cost about the same as before (3–13% more for the checks), and filtered-out calls are unchanged.
- **`logger.level()` returns the level**: registering a level now returns its `Level` instead of `None`, `no` may be passed positionally, and re-registering keeps the existing color and icon unless new ones are given. Changing the `no` of a built-in level raises `TypeError` (as in loguru); a custom level re-registered under a new `no` releases the old one.
- **Messages logged from inside a callable sink are delivered**: a sink that itself calls `logger.info(...)` used to have those nested messages dropped.
- **`configure(levels=...)` entries without `no` update existing levels**: previously they were silently skipped; an unknown name now raises `ValueError`.
- **logust's frames are left out of tracebacks**: the `catch_wrapper` frame added by `@logger.catch` no longer appears. `opt(backtrace=True)` / `opt(diagnose=True)` tracebacks now hide only logust's own modules; before, they hid every frame whose path contained `logust`, including application code in such a directory.
- **Callable sinks skip markup parsing for messages without `<`**: a `{message}`-only callable sink is a few percent faster.
- **`record["elapsed"]` is a `timedelta`** in filters, patchers, and callbacks. Its `str()` and `{elapsed}` still give `HH:MM:SS.mmm`, but comparing it to a string no longer matches. `time`, `elapsed`, `thread`, and `process` are not JSON-serializable, so a callback passing the whole record to `json.dumps()` needs `default=str` or a subset of keys. Bound values named `time`, `module`, `thread`, `process`, or `level_no` now stay only in `record["extra"]` instead of also shadowing the top-level key
- **`record["exception"]` is always present**: `None` when there is no exception (it was missing before), as documented. It is still the traceback text, not loguru's `(type, value, traceback)` tuple
- **Patcher records gain fields**: `time`, `timestamp` (previously `""`), `elapsed`, `thread`, and `process` are available, computed on first access so patchers that only touch `record["extra"]` cost the same as before, and `record["level"]` has `.no`. Changes to `message`, `extra`, and `exception` are still the only ones applied
- **Caller file path is collected without extra cost**: the Python side now passes the code object's path and Rust derives the basename, which also makes formats with caller info slightly faster. `{file}` and the record dicts' `file` key are still the basename.
- **Faster file and console output**: the default `{time}` is written directly instead of through chrono's strftime parser, colorized tokens are rendered in place instead of through a temporary string each, padded levels and numbers are pushed as digits, and locked writes of rotating sinks no longer `dup()` the lock file per record. Output is byte-identical. Measured per record on a release build (median of alternating runs, noise 2-5%): default file sink 1.16 → 0.88 µs, `serialize=True` 1.19 → 0.98 µs, rich template (`{thread}`, `{process}`, `{elapsed}`) 1.60 → 1.27 µs, colorized file sink 1.45 → 0.96 µs, colorized console 2.12 → 1.66 µs, `enqueue=True` 1.17 → 0.92 µs. `{message}`-only sinks are unchanged.
- **Less Python overhead per message**: the dispatch path skips the patcher call when no patcher is set, reads cached collection requirements inline, memoizes which kwargs a message template consumes, builds `bind()` loggers without re-running `__init__`, and binds the module-level functions (`logust.info(...)`) once at import. Measured per call with a file sink: `logger.info("msg")` with `{message}` about 25% faster (0.48 → 0.36 µs) and about 9% with the default format, `logust.info(...)` 47%, `logger.info("x {y}", y=1)` 33%, `opt(lazy=True)` 31%, `bind(k=1).info(...)` 29%, `log("INFO", ...)` 21%, `patch(f).info(...)` 14%, callable sinks 17%. Output and caller depth are unchanged; filtered-out calls and the default console handler cost the same as before.

### Fixed
- **File sinks lost lines at normal exit when a filter or a callable sink was set**: `logger.add("f.log", filter=lambda r: True); logger.info("one")` left `f.log` empty unless `logger.complete()` was called, for sync and `enqueue=True` sinks alike, and so did adding any callable sink. Buffered lines were only written when the logger was freed during interpreter teardown, and a filter or sink defined in a module refers to that module's globals, which hold the logger: the reference cycle kept it alive past finalization, so it was never freed. Buffered sync sinks and `enqueue=True` sinks are now written from an `atexit` handler registered at import, which runs after the application's own `atexit` handlers and does not depend on the logger being freed. Logging speed is unchanged.
- **`enqueue=True` sinks flush within 100 ms under a steady trickle of messages**: the background writer only flushed after 100 ms without any message, so a message every few tens of milliseconds kept lines in its buffer until 8 KB had accumulated. Every line now reaches the file at most 100 ms after it was logged.
- **File lines are never split between two writes**: a line that didn't fit in the rest of the 8 KB buffer, or was longer than it, went to the file in two `write()` calls, so another process appending to the same file could land in the middle of it. The buffer is now written first, and a line longer than the buffer is written in one call.
- **String and dict filters work** (**breaking** for code that passed them): `add(filter="mypkg")` and `add(filter={"": "WARNING", "mypkg": "DEBUG", "noisy": False})` were accepted and had no effect, so every record reached the sink. They now follow loguru: a string keeps the records of that module and its submodules (`"a"` matches `a` and `a.b`, not `ab`; `""` matches all), and a dict sets a minimum level per module, decided by the closest parent module in the dict, with `""` as the default and values given as a level name, a number, `True` (all) or `False` (none). Both are checked in Rust on the caller's module name, without building the record dict or calling Python: a file sink with `filter="mypkg"` costs about 0.53 µs per message, against 1.3 µs for the equivalent `lambda r: r["name"] ...` function and 0.21 µs with no filter (the difference is the caller lookup the module name needs, the same as `{name}` in a format). They work on file, console, stream and callable sinks and in `configure(handlers=[...])`, and the type hints of `add()` and `HandlerConfig` accept them (the new `logust.FilterType` alias). Invalid filters now raise at `add()` time like loguru: `TypeError` for a filter that is not a string, dict or callable, a non-string dict key or a dict value of another type, and `ValueError` for an unknown level name, a negative level or the built-in `filter()` function.
- **A filter that raises drops the record and follows `catch=`** (**breaking**): on file and console sinks, an exception raised by a `filter` function used to be swallowed and the record was written anyway. Now, as in loguru, the record is not written to that sink, and the error follows the sink's `catch=` policy: dropped silently with the default `None`, reported to stderr as `--- Logging error in Logust Handler #<id> ---` with the traceback for `True`, and raised from the logging call (after the other sinks got the record) for `False`. Callable and stream sinks already behaved this way.
- **Console sinks no longer crash on a closed pipe**: when the reader of stdout or stderr went away (`python app.py | head -1`), the next `logger.info(...)` to `sys.stdout`, `sys.stderr` or the default handler escaped as `pyo3_runtime.PanicException` (a `BaseException`) and took the application down. Console writes now return the error to the sink's `catch` policy: `None` (default) keeps running and drops the output, `True` prints one report per dropped message, `False` raises `BrokenPipeError`. Output timing is unchanged (one line-buffered write per message), and the `catch=True` report and the `enqueue=True` background writer no longer panic when stderr itself is broken.
- **Unsupported `rotation` / `retention` strings are rejected**: values the file sink does not understand, such as loguru's `rotation="1 week"` or `"12:00"` and `retention="1 week"`, were accepted and then never rotated or cleaned anything up. `add()` now raises `ValueError` listing the supported forms (`"daily"`, `"hourly"`, sizes like `"500 MB"`; retention as a file count or `"N days"`).
- **`enqueue=True` in a forked child on macOS**: a child forked after the parent had run an `enqueue=True` sink crashed with SIGTRAP when it added its own `enqueue=True` sink, because Rust's thread parking on macOS uses libdispatch, which traps after fork(). Sinks created in a forked child on macOS now write synchronously, as inherited sinks already did.
- **Coroutine function sinks are rejected**: `add()` raises `TypeError` for `async def` sinks (and async callables) instead of accepting them and never awaiting the coroutine.
- **`opt()` formats the message once**: `logger.opt().info("{} {user}", value, user="bob")` no longer raises `KeyError`, and braces inside a positional value are no longer re-interpreted as placeholders.
- **`{time:<spec>}` follows the spec**: loguru time tokens (`YYYY-MM-DD HH:mm:ss.SSS`, `A`, `ZZ`, `[escapes]`, `!UTC`, ...) and `%` strftime specs were ignored: file and console sinks wrote `{time:...}` literally and callable sinks wrote the full RFC 3339 timestamp. The spec is compiled once when the handler is added, and an invalid spec raises `ValueError`. Plain `{time}` is unchanged.
- **`contextualize()` is context-local**: it swapped the shared logger's context in place, so concurrent asyncio tasks and threads saw each other's values and a block exiting restored another block's stale snapshot; with the Starlette/FastAPI middleware, handler lines under concurrent requests carried another request's `request_id`. The values now live in a `contextvars` variable, as in loguru: each thread and task sees only its own blocks (and those inherited from the task that started it), nested blocks merge and restore correctly, and the values apply to every logger, bound or not, and to `logust.info(...)`. `extra` follows loguru's precedence: `contextualize()` values, then `bind()` values, then the message's keyword arguments. The block still yields the logger. A plain `logger.info("msg")` inside a block stays on the Rust fast path with a per-thread cache of the merged context; measured per call with a file sink (median of alternating runs, noise about 3%), logging inside a block costs the same as outside (0.21 µs with `{message}`), and the cost outside any block is unchanged.
- **Time-based rotation across daylight saving changes**: `rotation="daily"` and `"hourly"` (and the `timedelta` / `time(0, 0)` forms) stopped rotating for good when the next boundary was a wall-clock time that repeats (clocks fall back) or does not exist (clocks spring forward), which every zone with DST hits for `"hourly"` and zones that change at midnight, such as `America/Santiago` or `America/Havana`, hit for `"daily"`. A repeated boundary now rotates once, at its first occurrence, and a skipped boundary rotates at the transition itself, as in loguru. If the boundary cannot be resolved at all, the sink falls back to one hour or one day after the previous rotation instead of never rotating again.
- **Log files from an earlier period rotate on the first write**: a `"daily"` or `"hourly"` sink added over a non-empty file that was last written before the current boundary (for example by yesterday's run) rotates it on the first write, as loguru does. Previously the old content stayed in the file until the next boundary, and short-lived processes that never ran across one never rotated.

## [0.5.0] - 2026-10-01

### Added
- **Stream sinks**: `logger.add()` accepts any object with a callable `write()` (e.g. `io.StringIO`, a redirected `sys.stdout`). Only `sys.__stdout__` / `sys.__stderr__` use the Rust fast path. Item 1 from issue #59 (#64)
- **`colorize` for every sink type**: callable and file sinks accept `colorize=True` (level colors, token styles, message markup). Item 2 from issue #59 (#65)
- **`rich` progress bar example**: `examples/09_rich_progress.py` logs above a live progress bar. (#65)

### Changed
- **Color markup is stripped from non-colorized output**: Item 3 from issue #59 (#61)
- **Stream `colorize` auto-detection follows loguru**: `NO_COLOR`, `FORCE_COLOR`, CI, PyCharm, Jupyter, and `TERM=dumb` are honored before `isatty()`. `serialize=True`, file, and callable sinks default to no color. (#65)

### Fixed
- **Color markup in the `format` string**: tags such as `<green>{time}</green>` and loguru's `<level>...</level>` are rendered when colorized and stripped otherwise, on every sink type. A token inside markup takes the markup's color instead of its default style. (#66)
- **Callable sinks include tracebacks**: formatted callable sinks now append the exception text, the same as file and console sinks. (#64)

## [0.4.2] - 2026-08-06

### Changed
- **Dropped the unused `parking_lot` build dependency**: sink, level, and logger state has used `std::sync` primitives since the `fork()`-safety work in 0.3.1, so `parking_lot` was no longer referenced anywhere in `src/` and was not pulled in transitively either. Removing it shrinks the build graph for anyone compiling Logust from source; no runtime or API behavior changes. The contributing guide now documents `std::sync` as the expected lock choice. (#56)

## [0.4.1] - 2026-06-14

### Fixed
- **Free-threaded release CI targets supported interpreters and platforms**: release wheel builds no longer target unsupported Python 3.13t, keep Python 3.14t free-threaded validation, and add Windows 3.14t free-threaded wheels for x64, x86, and arm64. (#48)

## [0.4.0] - 2026-06-14

### Added
- **Canonical request events for web integrations**: `logust.contrib` now provides `canonical_event()`, `add_event_fields()`, `clear_event_fields()`, `get_event_fields()`, `get_current_event()`, and `TailSampler`, and Starlette/FastAPI middleware can emit one `http.request` event per request with request/response fields, endpoint-enriched extras, and tail sampling for errors and slow requests. (#38)

### Changed
- **JSON extra values handle more Python types**: `serialize=True` now emits `bytes` / `bytearray` extras as UTF-8 strings with replacement for invalid bytes, `set` / `frozenset` extras as arrays, `datetime` / `date` / `time` extras as `.isoformat()` strings, and `Enum` extras via their `.value` converted with the same rules. Text formatting (`{extra[key]}`) and Python callback records still use the existing `str(value)` view. Other object types such as `Decimal`, `UUID`, `Path`, and `complex` continue to fall back to `str(value)` in JSON.

## [0.3.2] - 2026-05-07

### Added
- **Loguru-style kwargs-to-extra in log methods**: `logger.info("user {id}", id=1, action="x")` now formats the message with `str.format` and attaches any kwargs not consumed by the message placeholders to `record["extra"]` for that call only (no persistent bind). Works on `trace` / `debug` / `info` / `success` / `warning` / `error` / `fail` / `critical` / `log` / `exception`. When the level is disabled, `message.format(**kwargs)` is skipped entirely via the existing `min_level` early-return, so disabled-level calls never trigger format work or `__format__`-side effects. Field root detection treats `{0abc}` and other non-decimal roots as keyword references. Implementation is Python-only — no Rust or `.pyi` changes — and per-call extra values are coerced to strings via the same path as `bind()`. (#25)
- **`logust.contrib.starlette` honors incoming `x-request-id` header**: `RequestLoggerMiddleware` now propagates the upstream `x-request-id` header value as the request id when present, falling back to the existing 8-char `uuid4` otherwise. Improves log correlation across reverse proxies. Visible behavior change for users behind proxies that already set the header — log ids will look different from before. (#28)
- **Optional extras `[starlette]` and `[fastapi]`**: `pip install "logust[starlette]"` / `pip install "logust[fastapi]"` install the framework alongside Logust so `logust.contrib.starlette` works without extra steps. (#29)

### Fixed
- **Patcher pipeline runs before handlers see the record**: `Logger.patch()` previously registered a callback that was never invoked before records reached filters or sinks, so security-sensitive transforms (e.g. token redaction) were silently dropped. `_log_with_level` and the dynamic-level `log()` path now run patchers before binding extras, normalize patched-extra keys to `str` for the Rust binder, and blank removed keys (`""`) so a patcher can hide a value previously bound via `bind()` / `contextualize()`. Behavior fix: code that relied on the silent drop (unlikely) will now see patchers run. (#26)
- **Starlette middleware no longer leaks secrets via query strings or partial JSON bodies**: `query_params` was logged as a plain `dict(...)`, exposing `access_token` / `password` / etc. in cleartext. Body masking ran *after* truncation, so a request that exceeded `max_body_size` could still log the unmasked head. Query params are now masked through the same sensitive-key check as headers, multi-value params are preserved, and bodies are masked first then truncated. (#26)
- **File retention no longer deletes unrelated same-stem files**: The retention scan in `src/sink.rs` used `filename.starts_with(stem)`, so a sibling like `app.keep`, `app.log.bak`, or even `application.log` next to `app.log` was eligible for deletion. Matching is now strict: only filenames matching the generated rotation pattern `{stem}.{YYYY-MM-DD_HH-MM-SS}_{micros}.pid{N}.{ext}[.gz]` are considered. (#26)

### Changed
- **`RequestLoggerMiddleware` rejects negative `max_body_size`**: `__init__` now raises `ValueError` when `max_body_size < 0` instead of silently producing surprising slicing behavior. (#28)

## [0.3.1] - 2026-04-23

### Fixed
- **`FileSink::drop` panic in forked children (`enqueue=True`)**: When a process using an `enqueue=True` file handler was forked (e.g. via `multiprocessing.Process`), the child inherited the parent's `JoinHandle` pointing at a background writer thread that does not survive `fork()`. Calling `logger.remove()` (or exit cleanup) in the child triggered `threads should not terminate unexpectedly`. `FileSink` now records its creation PID and skips the `JoinHandle::join` in non-original processes, preventing the panic. (#22)
- **Fork-safe file sinks across parent/child processes**: On Unix, `FileSink` now registers async sinks in a global registry and uses a `pthread_atfork(prepare)` hook to pause writer threads before `fork()`, avoiding macOS `libdispatch` SIGTRAP from inheriting live threads. The parent resumes its async writer on the next use; forked children downgrade an inherited `enqueue=True` backend to a fresh synchronous `BufWriter` on their first write instead of reviving the parent's thread and channel, and `mem::forget` the inherited handle/sender/buffer so no cleanup ever runs against parent-owned state. Multiple forked processes can keep appending to the same file sink, and re-forking a child no longer reintroduces the original join panic. (#22)
- **Cross-process rotation and `max_size`**: Rotation is now coordinated across processes with `flock` on a sibling `<path>.lock` file — writers take `LOCK_SH` for each write while the rotator takes `LOCK_EX`, so `rename` / `compress` / retention only run once every other process has released the old inode. Writers detect the inode change via `stat` and reopen the file on their next write, so no lines are lost when multiple processes share the sink. `max_size` also re-checks the real file size with `fs::metadata` after the atomic fast path, so size-based rotation no longer undercounts concurrent writes from other processes.
  Follow-up hardening: async shutdown stops the writer by dropping the sender instead of enqueueing a blocking `Shutdown`, `pthread_atfork(prepare)` uses `try_lock` best-effort shutdown without temporary allocation, and the sink / level / logger state uses `std::sync` primitives instead of `parking_lot` to keep inherited mutex state well-defined across `fork()`.

## [0.3.0] - 2026-04-11

### Performance
- **Formatting hot path (Rust, non-color)**: `format_record_template` writes padded level, line, thread, process, and elapsed into the output buffer with `std::fmt::Write` where possible, avoiding per-token `String` / `format!` temporaries; colorized branches unchanged. `format_template` skips time/level/message work when those tokens are absent (`TokenRequirements`). Added `benchmarks/bench_format_record.py` for a rich-template throughput check.
- **Formatted callable sink (built-in `logger.add`, `filter=None`, `serialize=False`)**: Rust distinguishes raw `add_callback` from formatted sinks and builds a **minimal record dict** per template flags (see `ParsedCallableTemplate::lightweight_requirements_for_rust()`), instead of always calling `build_record_dict`. Python still runs `ParsedCallableTemplate.format()` for full template/spec compatibility. Nested `record["extra"]` is populated only when `extra[...]` tokens are used (no duplicate flat extra keys on the lightweight path). Custom-level logs (`_log_custom`) keep the previous `build_custom_record_dict` path for all callbacks.
- **`update_requirements_cache` (Rust)**: Merges per-sink `FormattedSinkRequirements` into `TokenRequirements` instead of forcing `TokenRequirements::all()` whenever any callback exists; raw callbacks still force the full requirement set.
- **Non-color `format_record_template` (Rust)**: Avoids an extra `String` allocation for `{level}` / `{message}` when ANSI coloring is off; colorized output still reuses precomputed strings for repeated tokens.
- **`is_level_enabled()` (Rust)**: Uses the existing `cached_min_level` atomic instead of scanning every handler and callback, so enablement checks are O(1). This makes disabled `logger.opt(lazy=True).…` cheap even with large sink lists. Added regression tests (callback-only and `remove_callback`) and `benchmarks/bench_lazy_is_level.py`.
- **Filter fast path (Rust)**: Logs no longer enter the GIL path solely because a *lower-priority* handler has a Python `filter`. Handler filters run only after the handler's level gate passes. Removed the unused `cached_has_filters` cache; token requirements still treat any present filter as requiring full record fields for Python dict building.

## [0.2.1] - 2025-12-27

### Added
- `CollectOptions` for per-handler information collection control
- Callable sinks with custom format templates
- `{thread}`, `{process}`, `{file}`, `{elapsed}` format tokens

### Performance
- **14x faster than loguru on average** (up from 1.9x in 0.1.0)
- **4x faster than Python logging on average**
- Cached requirements computation (O(1) hot path)
- Cached `has_filters` flag in Rust (eliminates per-log iteration)
- Lazy token value generation for callable sinks
- Pre-aggregated CollectOptions to avoid per-log dictionary traversal
- Optimized kwargs passing in hot path

## [0.2.0] - 2025-12-25

### Added

#### Caller Information
- Caller info (module name, function name, line number) in log output
- New format tokens: `{name}`, `{function}`, `{line}`
- Default format now includes caller info: `{time} | {level:<8} | {name}:{function}:{line} - {message}`
- Caller info included in JSON serialized output

#### Console Sink Support
- `logger.add(sys.stdout)` and `logger.add(sys.stderr)` support
- `colorize` parameter for console handlers
- Auto-detect colorize based on TTY when not specified

### Changed
- `opt(depth=N)` now correctly adjusts caller frame for caller info
- Performance optimization: level check before frame capture

### Fixed
- Caller info now shows correct location through `opt()`, `exception()`, `catch()` wrappers
- Thread-safe colorization (removed global `set_override`)

## [0.1.0] - 2025-01-XX

### Added

#### Core Features
- 8 log levels: TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, FAIL, CRITICAL
- Colored console output with automatic terminal detection
- File output with buffered writing

#### File Management
- Size-based rotation (`"500 MB"`, `"1 GB"`)
- Time-based rotation (`"daily"`, `"hourly"`)
- Retention policies (by days or file count)
- Gzip compression for rotated files
- Async file writing with `enqueue=True`

#### Formatting
- JSON serialization with `serialize=True`
- Custom format templates with placeholders
- Color markup support (`<red>`, `<bold>`, etc.)

#### Context & Binding
- `bind()` for permanent context attachment
- `contextualize()` context manager for temporary context
- Extra fields included in JSON output

#### Exception Handling
- `catch()` decorator for automatic exception logging
- `exception()` method for logging with traceback
- `opt(exception=True)` for capturing current exception
- `opt(diagnose=True)` for variable inspection
- `opt(backtrace=True)` for extended stack traces

#### Advanced Features
- Custom log levels with `level()`
- Log callbacks with `add_callback()`
- Handler filtering with `filter` parameter
- Lazy evaluation with `opt(lazy=True)`
- `configure()` for batch configuration
- Log file parsing with `parse()` and `parse_json()`

#### Developer Experience
- Full type annotations (PEP 561 compatible)
- loguru-compatible API for easy migration
- Comprehensive test suite

### Performance
- Rust-powered core for high throughput
- 1.9x faster than loguru on average
- 1.3x faster than Python standard logging
- Lock-free fast path for filtered messages

[Unreleased]: https://github.com/yamaaaaaa31/logust/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/yamaaaaaa31/logust/compare/v0.4.2...v0.5.0
[0.4.2]: https://github.com/yamaaaaaa31/logust/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/yamaaaaaa31/logust/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/yamaaaaaa31/logust/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/yamaaaaaa31/logust/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/yamaaaaaa31/logust/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/yamaaaaaa31/logust/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/yamaaaaaa31/logust/releases/tag/v0.2.1
[0.2.0]: https://github.com/yamaaaaaa31/logust/releases/tag/v0.2.0
[0.1.0]: https://github.com/yamaaaaaa31/logust/releases/tag/v0.1.0
