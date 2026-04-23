# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/yamaaaaaa31/logust/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/yamaaaaaa31/logust/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/yamaaaaaa31/logust/releases/tag/v0.2.1
[0.2.0]: https://github.com/yamaaaaaa31/logust/releases/tag/v0.2.0
[0.1.0]: https://github.com/yamaaaaaa31/logust/releases/tag/v0.1.0
