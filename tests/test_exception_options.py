"""Per-handler ``backtrace`` / ``diagnose`` for logged exceptions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger


@pytest.fixture
def logger() -> Logger:
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.remove()
    return logger


def _fail(value: int) -> float:
    divisor = 0
    return value / divisor


def _log_exception(logger: Logger) -> None:
    try:
        _fail(42)
    except ZeroDivisionError:
        logger.exception("failed")


def test_default_handler_gets_plain_traceback(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message}")

    _log_exception(logger)

    (text,) = messages
    assert "Traceback (most recent call last):" in text
    assert "ZeroDivisionError: division by zero" in text
    assert "| divisor = 0" not in text


def test_diagnose_handler_shows_variables(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message}", diagnose=True)

    _log_exception(logger)

    (text,) = messages
    assert "| divisor = 0" in text
    assert "| value = 42" in text


def test_each_handler_gets_its_own_variant(logger: Logger, tmp_path: Path) -> None:
    plain: list[str] = []
    diagnosed: list[str] = []
    backtraced: list[str] = []
    log_file = tmp_path / "diag.log"
    logger.add(plain.append, format="{message}")
    logger.add(diagnosed.append, format="{message}", diagnose=True)
    logger.add(backtraced.append, format="{message}", backtrace=True)
    logger.add(log_file, format="{message}", diagnose=True)

    _log_exception(logger)
    logger.complete()

    assert "| divisor" not in plain[0]
    assert "| divisor = 0" in diagnosed[0]
    assert "| divisor" not in backtraced[0]
    # Backtrace includes the frames above the one that caught the exception
    assert "test_each_handler_gets_its_own_variant" in backtraced[0]
    assert "test_each_handler_gets_its_own_variant" not in plain[0]
    assert "| divisor = 0" in log_file.read_text(encoding="utf-8")


def test_no_exception_path_is_unchanged(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message}", diagnose=True, backtrace=True)

    logger.info("hello")

    assert messages == ["hello"]


def test_catch_uses_handler_variant_and_hides_wrapper(logger: Logger) -> None:
    plain: list[str] = []
    diagnosed: list[str] = []
    logger.add(plain.append, format="{message}")
    logger.add(diagnosed.append, format="{message}", diagnose=True)

    @logger.catch
    def divide(numerator: int) -> float:
        return numerator / 0

    divide(7)

    assert "catch_wrapper" not in plain[0]
    assert "ZeroDivisionError" in plain[0]
    assert "| numerator = 7" in diagnosed[0]
    assert "catch_wrapper" not in diagnosed[0]


def test_opt_exception_uses_handler_variant(logger: Logger) -> None:
    plain: list[str] = []
    diagnosed: list[str] = []
    logger.add(plain.append, format="{message}")
    logger.add(diagnosed.append, format="{message}", diagnose=True)

    try:
        _fail(1)
    except ZeroDivisionError:
        logger.opt(exception=True).warning("careful")

    assert "| divisor" not in plain[0]
    assert "| divisor = 0" in diagnosed[0]


def test_opt_diagnose_applies_to_every_handler(logger: Logger) -> None:
    plain: list[str] = []
    backtraced: list[str] = []
    logger.add(plain.append, format="{message}")
    logger.add(backtraced.append, format="{message}", backtrace=True)

    try:
        _fail(1)
    except ZeroDivisionError:
        logger.opt(diagnose=True).error("both")

    assert "| divisor = 0" in plain[0]
    assert "| divisor = 0" in backtraced[0]
    # Only the backtrace handler shows pytest's frames above the test function
    assert "pytest_pyfunc_call" in backtraced[0]
    assert "pytest_pyfunc_call" not in plain[0]


def test_custom_level_routes_variants(logger: Logger) -> None:
    logger.level("NOTICE_EXC", no=27)
    plain: list[str] = []
    diagnosed: list[str] = []
    logger.add(plain.append, format="{message}")
    logger.add(diagnosed.append, format="{message}", diagnose=True)

    with logger.catch(level="NOTICE_EXC"):
        _fail(3)

    assert "| divisor" not in plain[0]
    assert "| divisor = 0" in diagnosed[0]


def test_filtered_and_serialized_sinks_get_their_variant(logger: Logger) -> None:
    filtered: list[str] = []
    serialized: list[str] = []
    logger.add(filtered.append, format="{message}", filter=lambda r: True, diagnose=True)
    logger.add(serialized.append, serialize=True, diagnose=True)

    _log_exception(logger)

    assert "| divisor = 0" in filtered[0]
    assert "| divisor = 0" in serialized[0]


def test_raw_callbacks_and_patchers_see_record_traceback(logger: Logger) -> None:
    raw: list[dict[str, object]] = []
    patched: list[str] = []
    messages: list[str] = []
    logger.add(messages.append, format="{message}", diagnose=True)
    logger.add_callback(raw.append, level="ERROR")

    def spy(record: dict[str, object]) -> None:
        patched.append(str(record["exception"]))

    try:
        _fail(1)
    except ZeroDivisionError:
        logger.patch(spy).exception("failed")

    # Callbacks and patchers see the record's (plain) traceback; the sink writes its own
    assert "| divisor" not in str(raw[0]["exception"])
    assert "| divisor" not in patched[0]
    assert "| divisor = 0" in messages[0]


def test_patcher_replacing_exception_applies_to_all(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message}", diagnose=True)

    def redact(record: dict[str, object]) -> None:
        record["exception"] = "redacted"

    patched = logger.patch(redact)
    try:
        _fail(1)
    except ZeroDivisionError:
        patched.exception("failed")

    assert messages == ["failed\nredacted"]


def test_explicit_exception_string_is_shared(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message}", diagnose=True)

    logger.error("failed", exception="custom text")

    assert messages == ["failed\ncustom text"]


def test_removed_handler_variant_is_forgotten(logger: Logger) -> None:
    messages: list[str] = []
    handler_id = logger.add(messages.append, format="{message}", diagnose=True)
    assert logger._inner.exception_variant_mask & 0b100
    logger.remove(handler_id)
    assert logger._inner.exception_variant_mask == 0


def test_configure_accepts_backtrace_and_diagnose(logger: Logger) -> None:
    messages: list[str] = []
    logger.configure(handlers=[{"sink": messages.append, "format": "{message}", "diagnose": True}])

    _log_exception(logger)

    assert "| divisor = 0" in messages[0]


def test_plain_traceback_matches_traceback_module(logger: Logger) -> None:
    import traceback

    messages: list[str] = []
    logger.add(messages.append, format="{message}")

    try:
        _fail(5)
    except ZeroDivisionError:
        expected = traceback.format_exc()
        logger.exception("failed")

    assert messages == [f"failed\n{expected}"]


def test_chained_exceptions_keep_both_tracebacks(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message}")

    @logger.catch
    def convert() -> None:
        try:
            _fail(1)
        except ZeroDivisionError as error:
            raise ValueError("bad input") from error

    convert()

    text = messages[0]
    assert "ZeroDivisionError: division by zero" in text
    assert "direct cause" in text
    assert "ValueError: bad input" in text
    assert "catch_wrapper" not in text


def test_set_exception_variant_rejects_invalid(logger: Logger) -> None:
    handler_id = logger.add(lambda _: None)
    with pytest.raises(ValueError):
        logger._inner.set_exception_variant(handler_id, 4)
    assert logger._inner.set_exception_variant(10**9, 1) is False


@pytest.mark.skipif(sys.version_info < (3, 11), reason="exception groups")
def test_exception_group_hides_wrapper(logger: Logger) -> None:
    messages: list[str] = []
    logger.add(messages.append, format="{message}")

    @logger.catch
    def many() -> None:
        raise ExceptionGroup("group", [ValueError("a"), KeyError("b")])  # noqa: F821

    many()

    assert "ExceptionGroup: group" in messages[0]
    assert "catch_wrapper" not in messages[0]


class _BadStr(Exception):
    def __str__(self) -> str:
        raise RuntimeError("str failed")


class _BadRepr:
    def __repr__(self) -> str:
        raise ValueError("repr failed")


class TestEnhancedRobustness:
    @staticmethod
    def _sinks(logger: Logger) -> tuple[list[str], list[str]]:
        plain: list[str] = []
        enhanced: list[str] = []
        logger.add(plain.append, format="{message}")
        logger.add(enhanced.append, format="{message}", backtrace=True, diagnose=True)
        return plain, enhanced

    def test_exception_whose_str_raises(self, logger: Logger) -> None:
        plain, enhanced = self._sinks(logger)

        with logger.catch():
            raise _BadStr()

        assert plain[0].startswith("An error occurred: <exception str() failed>\n")
        assert enhanced[0].endswith("_BadStr: <exception str() failed>")

    def test_chained_exceptions_are_kept(self, logger: Logger) -> None:
        _, enhanced = self._sinks(logger)

        try:
            try:
                raise KeyError("inner")
            except KeyError as exc:
                raise RuntimeError("outer") from exc
        except RuntimeError:
            logger.exception("chain")

        text = enhanced[0]
        assert "KeyError: 'inner'" in text
        assert "The above exception was the direct cause of the following exception:" in text
        assert text.endswith("RuntimeError: outer")

    @pytest.mark.skipif(sys.version_info < (3, 11), reason="ExceptionGroup needs 3.11")
    def test_exception_group_members_are_kept(self, logger: Logger) -> None:
        _, enhanced = self._sinks(logger)

        try:
            raise ExceptionGroup("grp", [ValueError("a"), KeyError("b")])  # noqa: F821
        except Exception:
            logger.exception("group")

        assert "ValueError: a" in enhanced[0]
        assert "KeyError: 'b'" in enhanced[0]

    def test_recursion_is_collapsed(self, logger: Logger) -> None:
        _, enhanced = self._sinks(logger)

        def recurse(depth: int) -> int:
            return recurse(depth + 1)

        try:
            recurse(0)
        except RecursionError:
            logger.exception("deep")

        assert "[Previous line repeated" in enhanced[0]
        # Outer frames (backtrace=True) included; uncollapsed it is hundreds of KB
        assert len(enhanced[0]) < 50_000

    def test_failing_repr_hides_only_that_local(self, logger: Logger) -> None:
        plain, enhanced = self._sinks(logger)

        def fail() -> object:
            bad = _BadRepr()
            secret = "s3cret"
            return bad, secret, 1 / 0

        try:
            fail()
        except ZeroDivisionError:
            logger.exception("locals")

        assert "| bad = <repr failed>" in enhanced[0]
        assert "| secret = 's3cret'" in enhanced[0]
        assert "s3cret'" not in plain[0].split("return bad")[0]
        assert "| secret" not in plain[0]

    def test_catch_message_is_not_markup(self, logger: Logger) -> None:
        plain, _ = self._sinks(logger)

        with logger.catch():
            raise ValueError("<b>x</b>")

        assert plain[0].startswith("An error occurred: <b>x</b>\n")
