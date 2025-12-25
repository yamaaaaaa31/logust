"""Tests for log parsing functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from logust import parse, parse_json

DEFAULT_PATTERN = r"(?P<time>[\d-]+ [\d:]+) \| (?P<level>\w+)\s+\| (?P<message>.*)"


class TestParse:
    """Test parse() function for text log files."""

    def test_parse_basic(self, sample_log_file: Path) -> None:
        """Test basic log file parsing."""
        pattern = r"(?P<time>[\d-]+ [\d:]+) \| (?P<level>\w+)\s+\| (?P<message>.*)"
        records = list(parse(str(sample_log_file), pattern))

        assert len(records) == 3
        levels = [r.get("level", "") for r in records]
        assert "INFO" in levels
        assert "DEBUG" in levels
        assert "ERROR" in levels

    def test_parse_with_custom_pattern(self, tmp_path: Path) -> None:
        """Test parsing with custom pattern."""
        log_file = tmp_path / "custom.log"
        log_file.write_text("INFO|2024-01-01|Message 1\n" "DEBUG|2024-01-02|Message 2\n")

        pattern = r"(?P<level>\w+)\|(?P<date>[\d-]+)\|(?P<message>.+)"
        records = list(parse(str(log_file), pattern))

        assert len(records) == 2
        assert records[0].get("level") == "INFO"
        assert records[1].get("level") == "DEBUG"
        assert records[0].get("message") == "Message 1"

    def test_parse_with_cast(self, tmp_path: Path) -> None:
        """Test parsing with type casting."""
        log_file = tmp_path / "cast.log"
        log_file.write_text("100|INFO|Message 1\n" "200|DEBUG|Message 2\n")

        pattern = r"(?P<count>\d+)\|(?P<level>\w+)\|(?P<message>.+)"
        records = list(parse(str(log_file), pattern, cast={"count": int}))

        assert len(records) == 2
        assert records[0].get("count") == 100
        assert records[1].get("count") == 200
        assert isinstance(records[0].get("count"), int)

    def test_parse_skips_non_matching_lines(self, tmp_path: Path) -> None:
        """Test that non-matching lines are skipped."""
        log_file = tmp_path / "mixed.log"
        log_file.write_text(
            "VALID|message1\n"
            "this line does not match\n"
            "VALID|message2\n"
            "\n"
            "VALID|message3\n"
        )

        pattern = r"(?P<type>\w+)\|(?P<text>.+)"
        records = list(parse(str(log_file), pattern))

        assert len(records) == 3

    def test_parse_empty_file(self, tmp_path: Path) -> None:
        """Test parsing empty file."""
        log_file = tmp_path / "empty.log"
        log_file.write_text("")

        pattern = r"(?P<level>\w+)"
        records = list(parse(str(log_file), pattern))
        assert len(records) == 0

    def test_parse_nonexistent_file(self, tmp_path: Path) -> None:
        """Test parsing non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            list(parse(str(tmp_path / "nonexistent.log"), r".*"))


class TestParseJson:
    """Test parse_json() function for JSON log files."""

    def test_parse_json_basic(self, sample_json_log_file: Path) -> None:
        """Test basic JSON log parsing."""
        records = list(parse_json(str(sample_json_log_file)))

        assert len(records) == 3
        levels = [r.get("level", "") for r in records]
        assert "INFO" in levels
        assert "DEBUG" in levels
        assert "ERROR" in levels

    def test_parse_json_fields(self, sample_json_log_file: Path) -> None:
        """Test that JSON fields are preserved."""
        records = list(parse_json(str(sample_json_log_file)))

        for record in records:
            assert "level" in record
            assert "message" in record
            assert "timestamp" in record

    def test_parse_json_strict_valid(self, sample_json_log_file: Path) -> None:
        """Test strict mode with valid JSON."""
        records = list(parse_json(str(sample_json_log_file), strict=True))
        assert len(records) == 3

    def test_parse_json_strict_invalid(self, tmp_path: Path) -> None:
        """Test strict mode with invalid JSON raises error."""
        log_file = tmp_path / "invalid.json"
        log_file.write_text('{"level": "INFO"}\n' "not valid json\n" '{"level": "DEBUG"}\n')

        with pytest.raises(ValueError, match="Invalid JSON"):
            list(parse_json(str(log_file), strict=True))

    def test_parse_json_lenient_invalid(self, tmp_path: Path) -> None:
        """Test lenient mode skips invalid JSON lines."""
        log_file = tmp_path / "mixed.json"
        log_file.write_text(
            '{"level": "INFO", "message": "Valid 1"}\n'
            "not valid json\n"
            '{"level": "DEBUG", "message": "Valid 2"}\n'
        )

        records = list(parse_json(str(log_file), strict=False))
        assert len(records) == 2
        assert records[0].get("message") == "Valid 1"
        assert records[1].get("message") == "Valid 2"

    def test_parse_json_empty_file(self, tmp_path: Path) -> None:
        """Test parsing empty JSON file."""
        log_file = tmp_path / "empty.json"
        log_file.write_text("")

        records = list(parse_json(str(log_file)))
        assert len(records) == 0

    def test_parse_json_with_extras(self, tmp_path: Path) -> None:
        """Test parsing JSON with extra fields."""
        log_file = tmp_path / "extras.json"
        log_file.write_text(
            '{"level": "INFO", "message": "Test", "user_id": 123, "action": "login"}\n'
        )

        records = list(parse_json(str(log_file)))

        assert len(records) == 1
        record = records[0]
        assert record.get("user_id") == 123
        assert record.get("action") == "login"

    def test_parse_json_skips_empty_lines(self, tmp_path: Path) -> None:
        """Test that empty lines are skipped."""
        log_file = tmp_path / "whitespace.json"
        log_file.write_text('{"level": "INFO"}\n' "\n" "   \n" '{"level": "DEBUG"}\n')

        records = list(parse_json(str(log_file)))
        assert len(records) == 2
