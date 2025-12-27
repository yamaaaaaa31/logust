# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/yamaaaaaa31/logust/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yamaaaaaa31/logust/releases/tag/v0.1.0
