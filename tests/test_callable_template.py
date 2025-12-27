"""Tests for ParsedCallableTemplate optimization.

Tests the pre-parsed template for callable sinks, which provides
efficient single-pass formatting instead of multiple .replace() calls.
"""

from __future__ import annotations

from logust._template import LiteralSegment, ParsedCallableTemplate, TokenSegment


class TestParsedCallableTemplateSegments:
    """Test template parsing into segments."""

    def test_literal_only(self) -> None:
        """Template with no tokens should have one literal segment."""
        template = ParsedCallableTemplate("Hello World")
        assert len(template._segments) == 1
        assert isinstance(template._segments[0], LiteralSegment)
        assert template._segments[0].text == "Hello World"

    def test_single_token(self) -> None:
        """Template with single token should parse correctly."""
        template = ParsedCallableTemplate("{message}")
        assert len(template._segments) == 1
        assert isinstance(template._segments[0], TokenSegment)
        assert template._segments[0].key == "message"
        assert template._segments[0].spec is None

    def test_token_with_spec(self) -> None:
        """Template with format spec should parse correctly."""
        template = ParsedCallableTemplate("{level:<8}")
        assert len(template._segments) == 1
        seg = template._segments[0]
        assert isinstance(seg, TokenSegment)
        assert seg.key == "level"
        assert seg.spec == "<8"

    def test_mixed_segments(self) -> None:
        """Template with literals and tokens should parse correctly."""
        template = ParsedCallableTemplate("{level} | {message}")
        assert len(template._segments) == 3
        assert isinstance(template._segments[0], TokenSegment)
        assert template._segments[0].key == "level"
        assert isinstance(template._segments[1], LiteralSegment)
        assert template._segments[1].text == " | "
        assert isinstance(template._segments[2], TokenSegment)
        assert template._segments[2].key == "message"

    def test_extra_token(self) -> None:
        """Template with extra[key] should parse correctly."""
        template = ParsedCallableTemplate("{extra[user_id]}")
        assert len(template._segments) == 1
        seg = template._segments[0]
        assert isinstance(seg, TokenSegment)
        assert seg.key == "extra"
        assert seg.is_extra is True
        assert seg.extra_key == "user_id"

    def test_extra_token_with_spec(self) -> None:
        """Template with extra[key]:spec should parse correctly."""
        template = ParsedCallableTemplate("{extra[user]:<10}")
        assert len(template._segments) == 1
        seg = template._segments[0]
        assert isinstance(seg, TokenSegment)
        assert seg.key == "extra"
        assert seg.is_extra is True
        assert seg.extra_key == "user"
        assert seg.spec == "<10"

    def test_all_standard_tokens(self) -> None:
        """All standard tokens should be recognized."""
        tokens = [
            "time",
            "level",
            "name",
            "module",
            "function",
            "line",
            "file",
            "elapsed",
            "thread",
            "process",
            "message",
        ]
        for token in tokens:
            template = ParsedCallableTemplate(f"{{{token}}}")
            assert len(template._segments) == 1
            seg = template._segments[0]
            assert isinstance(seg, TokenSegment)
            assert seg.key == token

    def test_unknown_token_as_literal(self) -> None:
        """Unknown tokens should be kept as literals."""
        template = ParsedCallableTemplate("{unknown}")
        assert len(template._segments) == 1
        # Unknown token is kept as literal text
        assert isinstance(template._segments[0], LiteralSegment)
        assert template._segments[0].text == "{unknown}"


class TestParsedCallableTemplateFormat:
    """Test template formatting."""

    def test_simple_format(self) -> None:
        """Basic formatting should work."""
        template = ParsedCallableTemplate("{level} | {message}")
        record = {
            "level": "INFO",
            "message": "Hello World",
        }
        result = template.format(record)
        assert result == "INFO | Hello World"

    def test_format_with_spec(self) -> None:
        """Format specifiers should be applied."""
        template = ParsedCallableTemplate("{level:<8}|{message}")
        record = {
            "level": "INFO",
            "message": "Test",
        }
        result = template.format(record)
        assert result == "INFO    |Test"

    def test_format_with_all_tokens(self) -> None:
        """All standard tokens should format correctly."""
        template = ParsedCallableTemplate(
            "{time} | {level:<8} | {name}:{function}:{line} | {message}"
        )
        record = {
            "timestamp": "2024-01-01T12:00:00",
            "level": "INFO",
            "name": "test_module",
            "function": "test_func",
            "line": 42,
            "message": "Test message",
        }
        result = template.format(record)
        assert "2024-01-01T12:00:00" in result
        assert "INFO" in result
        assert "test_module" in result
        assert "test_func" in result
        assert "42" in result
        assert "Test message" in result

    def test_format_with_extra(self) -> None:
        """Extra fields should be formatted correctly."""
        template = ParsedCallableTemplate("{extra[user]} - {message}")
        record = {
            "message": "Action performed",
            "extra": {"user": "alice"},
        }
        result = template.format(record)
        assert result == "alice - Action performed"

    def test_format_with_extra_spec(self) -> None:
        """Extra fields with format spec should work."""
        template = ParsedCallableTemplate("{extra[user]:<10}|{message}")
        record = {
            "message": "Test",
            "extra": {"user": "bob"},
        }
        result = template.format(record)
        assert result == "bob       |Test"

    def test_format_with_missing_extra(self) -> None:
        """Missing extra fields should be empty string."""
        template = ParsedCallableTemplate("{extra[missing]} | {message}")
        record = {
            "message": "Test",
            "extra": {},
        }
        result = template.format(record)
        assert result == " | Test"

    def test_format_thread_process(self) -> None:
        """Thread and process should format as name:id."""
        template = ParsedCallableTemplate("{thread} | {process}")
        record = {
            "thread_name": "MainThread",
            "thread_id": 12345,
            "process_name": "MainProcess",
            "process_id": 67890,
        }
        result = template.format(record)
        assert result == "MainThread:12345 | MainProcess:67890"

    def test_format_module_alias(self) -> None:
        """Module should be alias for name."""
        template = ParsedCallableTemplate("{module}")
        record = {
            "name": "my_module",
        }
        result = template.format(record)
        assert result == "my_module"

    def test_format_elapsed(self) -> None:
        """Elapsed token should work."""
        template = ParsedCallableTemplate("{elapsed} | {message}")
        record = {
            "elapsed": "00:05:30.123",
            "message": "Test",
        }
        result = template.format(record)
        assert result == "00:05:30.123 | Test"

    def test_format_missing_values_defaults(self) -> None:
        """Missing values should use sensible defaults."""
        template = ParsedCallableTemplate("{level} | {message}")
        record: dict = {}  # Empty record
        result = template.format(record)
        # Should not raise, uses empty string defaults
        assert result == " | "


class TestParsedCallableTemplateBraceHandling:
    """Test that braces in message content are handled correctly."""

    def test_message_with_braces_not_replaced(self) -> None:
        """Braces in message should not be interpreted as tokens."""
        template = ParsedCallableTemplate("{level} | {message}")
        record = {
            "level": "INFO",
            "message": "Error: {level} is invalid",
        }
        result = template.format(record)
        # The {level} in message should NOT be replaced
        assert result == "INFO | Error: {level} is invalid"

    def test_message_with_spec_preserves_braces(self) -> None:
        """Message with format spec should preserve braces in content."""
        template = ParsedCallableTemplate("{level} | {message:<30}")
        record = {
            "level": "INFO",
            "message": "{level} happened",
        }
        result = template.format(record)
        # Message should be padded and braces preserved
        assert "{level} happened" in result
        assert result.startswith("INFO | ")

    def test_message_with_multiple_braces(self) -> None:
        """Multiple brace patterns in message should all be preserved."""
        template = ParsedCallableTemplate("{message}")
        record = {
            "message": "{time} {level} {name} are tokens",
        }
        result = template.format(record)
        assert result == "{time} {level} {name} are tokens"


class TestParsedCallableTemplateEdgeCases:
    """Test edge cases."""

    def test_empty_template(self) -> None:
        """Empty template should produce empty output."""
        template = ParsedCallableTemplate("")
        result = template.format({})
        assert result == ""

    def test_adjacent_tokens(self) -> None:
        """Adjacent tokens without separator should work."""
        template = ParsedCallableTemplate("{level}{message}")
        record = {
            "level": "INFO",
            "message": "test",
        }
        result = template.format(record)
        assert result == "INFOtest"

    def test_leading_literal(self) -> None:
        """Template starting with literal should work."""
        template = ParsedCallableTemplate("PREFIX: {message}")
        record = {"message": "Hello"}
        result = template.format(record)
        assert result == "PREFIX: Hello"

    def test_trailing_literal(self) -> None:
        """Template ending with literal should work."""
        template = ParsedCallableTemplate("{message} :SUFFIX")
        record = {"message": "Hello"}
        result = template.format(record)
        assert result == "Hello :SUFFIX"

    def test_multiple_extra_keys(self) -> None:
        """Multiple extra keys should all work."""
        template = ParsedCallableTemplate("{extra[a]} {extra[b]} {extra[c]}")
        record = {
            "extra": {"a": "1", "b": "2", "c": "3"},
        }
        result = template.format(record)
        assert result == "1 2 3"

    def test_spec_with_complex_format(self) -> None:
        """Complex format specs should work."""
        template = ParsedCallableTemplate("{line:>5}")
        record = {"line": 42}
        result = template.format(record)
        assert result == "   42"

    def test_file_token(self) -> None:
        """File token should work."""
        template = ParsedCallableTemplate("{file}:{line}")
        record = {
            "file": "test.py",
            "line": 100,
        }
        result = template.format(record)
        assert result == "test.py:100"


class TestExtraKeyPatterns:
    """Test that extra keys with special characters work."""

    def test_extra_key_with_hyphen(self) -> None:
        """Extra key with hyphen should work."""
        template = ParsedCallableTemplate("{extra[user-id]} | {message}")
        record = {
            "message": "Test",
            "extra": {"user-id": "abc-123"},
        }
        result = template.format(record)
        assert result == "abc-123 | Test"

    def test_extra_key_with_dot(self) -> None:
        """Extra key with dot should work."""
        template = ParsedCallableTemplate("{extra[user.name]} | {message}")
        record = {
            "message": "Test",
            "extra": {"user.name": "Alice"},
        }
        result = template.format(record)
        assert result == "Alice | Test"

    def test_extra_key_unicode(self) -> None:
        """Extra key with unicode should work."""
        template = ParsedCallableTemplate("{extra[ユーザー]} | {message}")
        record = {
            "message": "Test",
            "extra": {"ユーザー": "太郎"},
        }
        result = template.format(record)
        assert result == "太郎 | Test"

    def test_extra_key_with_underscore(self) -> None:
        """Extra key with underscore should work (baseline)."""
        template = ParsedCallableTemplate("{extra[user_id]} | {message}")
        record = {
            "message": "Test",
            "extra": {"user_id": "123"},
        }
        result = template.format(record)
        assert result == "123 | Test"

    def test_extra_key_with_numbers(self) -> None:
        """Extra key with numbers should work."""
        template = ParsedCallableTemplate("{extra[field123]} | {message}")
        record = {
            "message": "Test",
            "extra": {"field123": "value"},
        }
        result = template.format(record)
        assert result == "value | Test"

    def test_extra_key_complex(self) -> None:
        """Extra key with complex pattern should work."""
        template = ParsedCallableTemplate("{extra[x-request.id_v2]} | {message}")
        record = {
            "message": "Test",
            "extra": {"x-request.id_v2": "req-123"},
        }
        result = template.format(record)
        assert result == "req-123 | Test"
