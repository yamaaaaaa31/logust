# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via one of the following methods:

1. **GitHub Private Vulnerability Reporting**: Use GitHub's [private vulnerability reporting](https://github.com/yamaaaaaa31/logust/security/advisories/new) feature.

2. **Email**: Contact the maintainers directly (if email is available in the repository).

### What to Include

When reporting a vulnerability, please include:

- **Description**: A clear description of the vulnerability
- **Impact**: The potential impact of the vulnerability
- **Steps to Reproduce**: Detailed steps to reproduce the issue
- **Affected Versions**: Which versions are affected
- **Possible Fix**: If you have suggestions for fixing the issue

### Response Timeline

- **Acknowledgment**: Within 48 hours of receiving your report
- **Initial Assessment**: Within 1 week
- **Resolution Timeline**: Depends on severity, but we aim for:
  - Critical: 24-48 hours
  - High: 1 week
  - Medium: 2 weeks
  - Low: Next release cycle

### What to Expect

1. **Acknowledgment**: We will acknowledge receipt of your report
2. **Communication**: We will keep you informed of our progress
3. **Credit**: We will credit you in the security advisory (unless you prefer anonymity)
4. **Coordinated Disclosure**: We will coordinate the disclosure timeline with you

## Security Best Practices for Users

When using Logust in your projects:

### File Permissions

- Ensure log files have appropriate permissions
- Avoid logging to world-writable directories
- Consider using `compression=True` for archived logs

### Sensitive Data

- **Never log sensitive data** such as passwords, API keys, or personal information
- Use the `filter` parameter to exclude sensitive records:

```python
def filter_sensitive(record):
    return "password" not in record.get("message", "").lower()

logger.add("app.log", filter=filter_sensitive)
```

### Log Injection

- Be cautious when logging user input
- Sanitize or validate user input before logging
- Use structured logging (JSON) when possible

### Production Recommendations

```python
from logust import logger

# Production configuration
logger.add(
    "app.log",
    level="INFO",           # Don't use DEBUG in production
    rotation="100 MB",      # Prevent disk exhaustion
    retention="30 days",    # Clean up old logs
    compression=True,       # Reduce storage
    serialize=True,         # Structured logs for analysis
)
```

## Dependency Security

Logust depends on:

- **Rust crates**: Regularly audited via `cargo audit`
- **Python packages**: Minimal runtime dependencies

We monitor for security advisories in our dependencies and update promptly when vulnerabilities are discovered.

## Security Updates

Security updates will be released as patch versions (e.g., 0.1.1, 0.1.2) and announced via:

- GitHub Security Advisories
- Release notes

We recommend always using the latest version of Logust.
