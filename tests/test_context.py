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

    def test_patch_basic(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test basic patcher function."""
        logger, log_file = logger_with_file

        def add_tag(record: dict[str, Any]) -> None:
            if "extra" not in record:
                record["extra"] = {}
            record["extra"]["tag"] = "patched"

        patched = logger.patch(add_tag)
        patched.info("Patched message")
        logger.complete()

        content = log_file.read_text()
        assert "Patched message" in content

    def test_patch_chain(self, logger_with_file: tuple[Logger, Path]) -> None:
        """Test chaining multiple patchers."""
        logger, log_file = logger_with_file

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
        logger.complete()

        content = log_file.read_text()
        assert "Multi-patched" in content

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
