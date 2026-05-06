# Logust Examples

Run examples from the repository root after installing Logust in editable mode:

```bash
maturin develop
python examples/01_basic_logging.py
```

## Available Examples

- `01_basic_logging.py`: levels and basic message formatting
- `02_file_output.py`: files, rotation, retention, compression, async writes
- `03_json_serialization.py`: JSON logs and parsing JSON logs back
- `04_context_binding.py`: `bind()` and `contextualize()`
- `05_exception_handling.py`: exceptions, `catch()`, `opt(exception=True)`
- `06_custom_levels.py`: custom level names, colors, and filtering
- `07_callbacks.py`: callbacks for metrics, alerts, and external services
- `08_fastapi_integration.py`: FastAPI canonical request events and tail sampling

## FastAPI Example

Install the web extra and `uvicorn`:

```bash
pip install "logust[fastapi]" uvicorn
python examples/08_fastapi_integration.py
```

Try a few requests:

```bash
curl -H "x-request-id: req-demo" "http://localhost:8000/users/123?plan=pro"
curl -X POST "http://localhost:8000/checkout?user_id=u_123"
curl "http://localhost:8000/error"
```

The example writes canonical JSON request events to `logs/app.json`.
