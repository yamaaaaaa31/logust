# Installation

Get Logust from PyPI in seconds, or build from source for local Rust changes.

## Requirements

!!! note "No Rust needed"
    Pre-built wheels available for all platforms. No Rust toolchain required.

- Python 3.10+
- Linux, macOS, Windows

## Install

=== "pip"
    ```bash
    pip install logust
    ```

=== "uv"
    ```bash
    uv add logust
    ```

=== "FastAPI"
    ```bash
    pip install "logust[fastapi]"
    ```

=== "Starlette"
    ```bash
    pip install "logust[starlette]"
    ```

=== "source"
    ```bash
    git clone https://github.com/yamaaaaaa31/logust.git
    cd logust

    uv venv && source .venv/bin/activate
    uv pip install maturin
    maturin develop --release
    ```
    !!! note "Rust required"
        Source builds require Rust stable and a working cargo toolchain.
        On Windows, activate with `.venv\\Scripts\\activate`.

## Optional extras

Install web framework integrations on demand:

=== "Starlette"
    ```bash
    pip install "logust[starlette]"
    ```

=== "FastAPI"
    ```bash
    pip install "logust[fastapi]"
    ```

These extras install the web framework alongside Logust so
`logust.contrib.starlette` and the `RequestLoggerMiddleware` work out of the
box.

## Verify

```bash
python -c "import logust; logust.info('Logust installed')"
```

## Next steps

- [Quick start](quick-start.md)
- [File output](../guide/file-output.md)
