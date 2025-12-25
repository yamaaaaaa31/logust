# Formatting

Make logs readable with templates, or switch to JSON.

!!! example "JSON for log aggregation"
    Use `serialize=True` for structured logging with Elasticsearch, Loki, etc.

## Default format

The default log format is:

```
{time} | {level} | {message}
```

Output:
```
2025-12-24 15:52:42.199 | INFO     | Hello, Logust!
```

## Custom format

Customize the format when adding a handler:

```python
from logust import logger

logger.add("app.log", format="{time} | {level} | {message}")
logger.add("simple.log", format="[{level}] {message}")
logger.add("minimal.log", format="{message}")
```

## Format tokens

| Token | Description | Example |
|-------|-------------|---------|
| `{time}` | Timestamp | `2025-12-24 12:00:00.123` |
| `{level}` | Log level name | `INFO` |
| `{level:<8}` | Aligned level | `INFO    ` |
| `{message}` | Log message | `Hello, world!` |
| `{extra[key]}` | Extra context fields | `{extra[user_id]}` |

### Extra fields

```python
from logust import logger

user_logger = logger.bind(user_id="123", action="login")
user_logger.info("User action")
```

Format usage:

```text
{time} | {level} | {message} | user={extra[user_id]}
```

## JSON output

For structured logging, use the `serialize` option:

```python
logger.add("app.json", serialize=True)
logger.info("User logged in")
```

Output:
```json
{
  "time": "2025-12-24T12:00:00.123456",
  "level": "INFO",
  "message": "User logged in"
}
```

### JSON with context

When using `bind()`, extra fields are included:

```python
logger.add("app.json", serialize=True)
user_logger = logger.bind(user_id="123", action="login")
user_logger.info("User action")
```

Output:
```json
{
  "time": "2025-12-24T12:00:00.123456",
  "level": "INFO",
  "message": "User action",
  "extra": {
    "user_id": "123",
    "action": "login"
  }
}
```

## Color markup

Add colors to console output using markup:

```python
from logust import logger

logger.info("<red>Error</red> in <blue>module</blue>")
logger.info("<green>Success!</green>")
logger.info("<bold>Important</bold> message")
```

### Available tags

| Tag | Description |
|-----|-------------|
| `<red>`, `<green>`, `<blue>`, etc. | Text colors |
| `<bold>` | Bold text |
| `<underline>` | Underlined text |
| `<bright_red>`, `<bright_green>`, etc. | Bright colors |

!!! note
    Color markup only works in console output, not in file handlers.
