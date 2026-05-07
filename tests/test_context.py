"""Tests for context binding (bind, contextualize, patch)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from logust import Logger


class TestBind:
    """Test bind() method."""

    def test_bind_single_value(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test binding a single value."""
        logger, log_file = logger_with_file

        bound = logger.bind(user_id="123")
        bound.info("User action")
        logger.complete()

        content = log_file.read_text()
        assert "User action" in content

    def test_bind_multiple_values(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test binding multiple values."""
        logger, log_file = logger_with_file

        bound = logger.bind(user_id="123", session="abc", role="admin")
        bound.info("Multi-context action")
        logger.complete()

        content = log_file.read_text()
        assert "Multi-context action" in content

    def test_bind_chain(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test chaining multiple bind() calls."""
        logger, log_file = logger_with_file

        bound = logger.bind(user="alice").bind(action="login")
        bound.info("Chained bind")
        logger.complete()

        content = log_file.read_text()
        assert "Chained bind" in content

    def test_bind_preserves_original(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test that bind() returns new logger, original unchanged."""
        logger, log_file = logger_with_file

        bound = logger.bind(extra="value")

        logger.info("Original logger")
        bound.info("Bound logger")
        logger.complete()

        content = log_file.read_text()
        assert "Original logger" in content
        assert "Bound logger" in content


class TestContextualize:
    """Test contextualize() context manager."""

    def test_contextualize_basic(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test basic contextualize usage."""
        logger, log_file = logger_with_file

        with logger.contextualize(request_id="abc"):
            logger.info("Inside context")

        logger.info("Outside context")
        logger.complete()

        content = log_file.read_text()
        assert "Inside context" in content
        assert "Outside context" in content

    def test_contextualize_nested(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test nested contextualize blocks."""
        logger, log_file = logger_with_file

        with logger.contextualize(level1="a"):
            logger.info("Level 1")
            with logger.contextualize(level2="b"):
                logger.info("Level 2")
            logger.info("Back to level 1")

        logger.complete()

        content = log_file.read_text()
        assert "Level 1" in content
        assert "Level 2" in content
        assert "Back to level 1" in content

    def test_contextualize_exception_cleanup(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test that contextualize cleans up on exception."""
        logger, log_file = logger_with_file

        try:
            with logger.contextualize(temp="value"):
                logger.info("Before exception")
                raise ValueError("Test error")
        except ValueError:
            pass

        logger.info("After exception")
        logger.complete()

        content = log_file.read_text()
        assert "Before exception" in content
        assert "After exception" in content


class TestPatch:
    """Test patch() method for record modification."""

    def test_patch_basic(self, fresh_logger: Logger) -> None:
        """Test basic patcher function."""
        logger = fresh_logger
        records: list[dict[str, Any]] = []
        logger.add_callback(records.append)

        def add_tag(record: dict[str, Any]) -> None:
            if "extra" not in record:
                record["extra"] = {}
            record["extra"]["tag"] = "patched"

        patched = logger.patch(add_tag)
        patched.info("Patched message")

        assert records[0]["message"] == "Patched message"
        assert records[0]["extra"]["tag"] == "patched"

    def test_patch_chain(self, fresh_logger: Logger) -> None:
        """Test chaining multiple patchers."""
        logger = fresh_logger
        records: list[dict[str, Any]] = []
        logger.add_callback(records.append)

        def add_first(record: dict[str, Any]) -> None:
            if "extra" not in record:
                record["extra"] = {}
            record["extra"]["first"] = "1"

        def add_second(record: dict[str, Any]) -> None:
            if "extra" not in record:
                record["extra"] = {}
            record["extra"]["second"] = "2"

        patched = logger.patch(add_first).patch(add_second)
        patched.info("Multi-patched")

        assert records[0]["message"] == "Multi-patched"
        assert records[0]["extra"]["first"] == "1"
        assert records[0]["extra"]["second"] == "2"

    def test_patch_applies_before_filtered_handlers(self, fresh_logger: Logger) -> None:
        """Patchers should run before handlers inspect the record."""
        logger = fresh_logger
        messages: list[str] = []

        def allow_patched(record: dict[str, Any]) -> bool:
            return record.get("extra", {}).get("tag") == "allow"

        logger.add(messages.append, format="{message}", filter=allow_patched)

        def add_tag(record: dict[str, Any]) -> None:
            record["extra"]["tag"] = "allow"

        logger.patch(add_tag).info("Allowed by patcher")

        assert messages == ["Allowed by patcher"]

    def test_patch_can_redact_bound_extra(self, fresh_logger: Logger) -> None:
        """Patchers should be able to inspect and update bound context."""
        logger = fresh_logger
        records: list[dict[str, Any]] = []
        logger.add_callback(records.append)

        def redact_token(record: dict[str, Any]) -> None:
            if record["extra"].get("access_token") == "SECRET":
                record["extra"]["access_token"] = "***"

        logger.bind(access_token="SECRET").patch(redact_token).info("redacted")

        assert records[0]["extra"]["access_token"] == "***"

    def test_patch_can_redact_contextualized_extra(self, fresh_logger: Logger) -> None:
        """Temporary context should be visible to patchers."""
        logger = fresh_logger
        records: list[dict[str, Any]] = []
        logger.add_callback(records.append)

        def redact_token(record: dict[str, Any]) -> None:
            if record["extra"].get("access_token") == "SECRET":
                record["extra"]["access_token"] = "***"

        patched = logger.patch(redact_token)
        with patched.contextualize(access_token="SECRET"):
            patched.info("redacted")

        assert records[0]["extra"]["access_token"] == "***"

    def test_patch_normalizes_extra_keys(self, fresh_logger: Logger) -> None:
        """Patch-created extra keys should be safe for the Rust binder."""
        logger = fresh_logger
        records: list[dict[str, Any]] = []
        logger.add_callback(records.append)

        def add_numeric_key(record: dict[str, Any]) -> None:
            record["extra"][123] = "numeric"

        logger.patch(add_numeric_key).info("normalized")

        assert records[0]["extra"]["123"] == "numeric"

    def test_patch_can_hide_bound_extra_key(self, fresh_logger: Logger) -> None:
        """Removing a patched extra key should hide the bound value from handlers."""
        logger = fresh_logger
        records: list[dict[str, Any]] = []
        logger.add_callback(records.append)

        def remove_token(record: dict[str, Any]) -> None:
            record["extra"].pop("access_token", None)

        logger.bind(access_token="SECRET").patch(remove_token).info("removed")

        assert records[0]["extra"]["access_token"] == ""

    def test_patch_preserves_original(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test that patch() returns new logger."""
        logger, log_file = logger_with_file

        def modifier(record: dict[str, Any]) -> None:
            pass

        patched = logger.patch(modifier)

        logger.info("Original")
        patched.info("Patched")
        logger.complete()

        content = log_file.read_text()
        assert "Original" in content
        assert "Patched" in content
