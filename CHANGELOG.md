# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial public release preparation
- Comprehensive documentation (README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY)
- Pre-commit hooks for code quality
- GitHub Issue and PR templates
- CI/CD workflows for testing and release

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
