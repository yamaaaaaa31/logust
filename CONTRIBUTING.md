# Contributing to Logust

Thank you for your interest in contributing to Logust! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [License](#license)

## Code of Conduct

Please be respectful and considerate in all interactions. We welcome contributors of all experience levels and backgrounds.

## Getting Started

### Prerequisites

- **Python 3.10+**
- **Rust (latest stable)** - Install via [rustup](https://rustup.rs/)
- **uv** (recommended) or pip for Python package management
- **maturin** for building Rust-Python bindings

### Development Setup

```bash
# Clone the repository
git clone https://github.com/yamaaaaaa31/logust.git
cd logust

# Create and activate virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install development dependencies
uv pip install maturin pre-commit

# Build the Rust extension in development mode
maturin develop

# Install pre-commit hooks
pre-commit install
pre-commit install --hook-type pre-push

# Verify installation
python -c "import logust; logust.info('Ready to contribute!')"
```

## Project Structure

```
logust/
├── src/                    # Rust source code
│   ├── lib.rs              # PyO3 module exports, PyLogger implementation
│   ├── level.rs            # LogLevel enum and custom level support
│   ├── handler.rs          # Console and File handlers
│   ├── sink.rs             # FileSink with async/sync writing
│   └── format.rs           # Format configuration and color markup
├── logust/                  # Python source code
│   ├── __init__.py         # Public API exports
│   ├── _logger.py          # Logger class (Python wrapper)
│   ├── _opt.py             # OptLogger for per-message options
│   ├── _parse.py           # Log file parsing utilities
│   ├── _traceback.py       # Enhanced traceback formatting
│   ├── _types.py           # Type definitions
│   └── _logust.pyi         # Type stubs for Rust extension
├── tests/                   # Test suite
│   └── test_*.py           # Unit tests
├── benchmarks/              # Performance benchmarks
├── docs/                    # Documentation (MkDocs)
├── Cargo.toml              # Rust dependencies
├── pyproject.toml          # Python project configuration
└── .pre-commit-config.yaml # Pre-commit hooks
```

## Making Changes

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### 2. Make Your Changes

- **Rust code**: Edit files in `src/`
- **Python code**: Edit files in `logust/`
- **Tests**: Add or modify tests in `tests/`

### 3. Rebuild After Rust Changes

```bash
maturin develop
```

### 4. Run Pre-commit Checks

```bash
pre-commit run --all-files
```

### 5. Run Tests

```bash
# Rust tests
cargo test

# Python tests
pytest tests/ -v

# All tests with coverage
pytest tests/ --cov=logust --cov-report=term-missing
```

## Pull Request Process

1. **Ensure all checks pass**: Pre-commit hooks and tests must pass
2. **Update documentation**: If adding features, update README.md and docstrings
3. **Write descriptive commit messages**: Use conventional commit format when possible
4. **Keep PRs focused**: One feature or fix per PR
5. **Respond to feedback**: Be open to suggestions and iterate

### Commit Message Format

```
type: short description

Longer description if needed.

- Bullet points for multiple changes
- Another change
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## Coding Standards

### Rust

- Format with `cargo fmt`
- Lint with `cargo clippy -- -D warnings`
- Follow [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/)
- Use `#[inline]` for small, hot functions
- Prefer `parking_lot` over `std::sync` for locks

### Python

- Format with `ruff format`
- Lint with `ruff check`
- Type check with `mypy`
- Follow [PEP 8](https://pep8.org/)
- Use type hints for all public APIs
- Write docstrings for public functions/classes

### General

- Comments in English only
- Keep functions focused and small
- Avoid unnecessary dependencies
- Consider performance implications

## Testing

### Adding Tests

- Place tests in `tests/test_*.py`
- Use descriptive test names: `test_feature_specific_behavior`
- Use fixtures from `tests/conftest.py`
- Test both success and error cases

### Running Specific Tests

```bash
# Run a specific test file
pytest tests/test_logger.py -v

# Run tests matching a pattern
pytest -k "test_bind" -v

# Run with verbose output
pytest -v --tb=long
```

### Benchmarks

```bash
# Run performance benchmarks
python benchmarks/bench_throughput.py
```

## Reporting Issues

When reporting bugs, please include:

1. **Python version**: `python --version`
2. **Rust version**: `rustc --version`
3. **OS and version**
4. **Minimal reproduction code**
5. **Expected vs actual behavior**
6. **Full error traceback** if applicable

## Feature Requests

For feature requests, please describe:

1. **The problem** you're trying to solve
2. **Proposed solution** with example usage
3. **Alternatives** you've considered
4. **Additional context** (links to similar features in other libraries)

## License

By contributing to Logust, you agree that your contributions will be licensed under the MIT License.

### What MIT License Means

The MIT License is a permissive open-source license that:

**Allows:**
- Commercial use
- Modification
- Distribution
- Private use
- Sublicensing

**Requires:**
- License and copyright notice must be included in all copies

**Does not require:**
- Source code disclosure
- Same license for derivative works

**Provides no warranty:**
- The software is provided "as is" without warranty of any kind

This means you can use Logust in any project (including proprietary software), modify it as you wish, and distribute your modifications. The only requirement is to include the original license and copyright notice.

For the full license text, see [LICENSE](LICENSE).

---

Thank you for contributing to Logust!
