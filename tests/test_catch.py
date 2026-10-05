"""Tests for logger.catch() as decorator and context manager (loguru parity)."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import Generator, Iterator
from pathlib import Path

import pytest

from logust import Logger, LogLevel
from logust._logust import PyLogger


@pytest.fixture
def logger_and_output() -> Generator[tuple[Logger, list[str]], None, None]:
    """Logger with a callable sink collecting ``level | function | message`` lines."""
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.disable()
    output: list[str] = []
    logger.add(output.append, format="{level} | {function} | {message}")
    yield logger, output
    logger.remove()


class TestCatchContextManager:
    """Test ``with logger.catch(): ...``."""

    def test_suppresses_and_logs(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, output = logger_and_output

        with logger.catch():
            raise ValueError("boom")

        assert len(output) == 1
        assert "ERROR" in output[0]
        assert "An error occurred: boom" in output[0]
        assert "ValueError" in output[0]

    def test_no_exception_logs_nothing(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, output = logger_and_output

        with logger.catch():
            pass

        assert output == []

    def test_reraise(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, output = logger_and_output

        with pytest.raises(RuntimeError, match="again"), logger.catch(reraise=True):
            raise RuntimeError("again")

        assert len(output) == 1

    def test_unmatched_exception_propagates(
        self, logger_and_output: tuple[Logger, list[str]]
    ) -> None:
        logger, output = logger_and_output

        with pytest.raises(KeyError), logger.catch(ValueError):
            raise KeyError("missing")

        assert output == []

    def test_points_at_with_block(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, output = logger_and_output

        def function_with_block() -> None:
            with logger.catch():
                raise ValueError("here")

        function_with_block()

        assert "| function_with_block |" in output[0]


class TestCatchBareDecorator:
    """Test ``@logger.catch`` without parentheses."""

    def test_bare_decorator(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, output = logger_and_output

        @logger.catch
        def risky(x: int) -> int:
            raise ValueError(f"bad {x}")

        assert risky(3) is None
        assert len(output) == 1
        assert "An error occurred: bad 3" in output[0]
        assert risky.__name__ == "risky"

    def test_bare_decorator_returns_value(
        self, logger_and_output: tuple[Logger, list[str]]
    ) -> None:
        logger, output = logger_and_output

        @logger.catch
        def ok() -> int:
            return 42

        assert ok() == 42
        assert output == []

    def test_bare_decorator_points_at_call_site(
        self, logger_and_output: tuple[Logger, list[str]]
    ) -> None:
        logger, output = logger_and_output

        @logger.catch
        def risky() -> None:
            raise ValueError("x")

        def call_site() -> None:
            risky()

        call_site()

        assert "| call_site |" in output[0]

    def test_bare_decorator_in_subprocess(self, tmp_path: Path) -> None:
        """Module-level ``@logger.catch`` reports the call site in a real file sink."""
        log_file = tmp_path / "test.log"
        code = f"""
from logust import logger
logger.remove()
logger.add({str(log_file)!r}, format="{{function}} - {{message}}")

@logger.catch
def risky_func():
    raise RuntimeError("oops")

def caller_of_risky():
    risky_func()

caller_of_risky()
logger.complete()
"""
        subprocess.run([sys.executable, "-c", code], check=True)

        content = log_file.read_text()
        assert "caller_of_risky - An error occurred: oops" in content


class TestCatchOptions:
    """Test onerror, exclude, default, and level."""

    def test_onerror_called_with_exception(
        self, logger_and_output: tuple[Logger, list[str]]
    ) -> None:
        logger, output = logger_and_output
        seen: list[BaseException] = []

        @logger.catch(onerror=seen.append)
        def risky() -> None:
            raise ValueError("err")

        risky()

        assert len(seen) == 1
        assert isinstance(seen[0], ValueError)
        assert len(output) == 1

    def test_onerror_context_manager(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, _ = logger_and_output
        seen: list[BaseException] = []

        with logger.catch(onerror=seen.append):
            raise KeyError("k")

        assert isinstance(seen[0], KeyError)

    def test_onerror_not_called_without_error(
        self, logger_and_output: tuple[Logger, list[str]]
    ) -> None:
        logger, _ = logger_and_output
        seen: list[BaseException] = []

        with logger.catch(onerror=seen.append):
            pass

        assert seen == []

    def test_exclude_propagates_without_logging(
        self, logger_and_output: tuple[Logger, list[str]]
    ) -> None:
        logger, output = logger_and_output
        seen: list[BaseException] = []

        @logger.catch(exclude=ValueError, onerror=seen.append)
        def risky() -> None:
            raise ValueError("excluded")

        with pytest.raises(ValueError, match="excluded"):
            risky()

        assert output == []
        assert seen == []

    def test_exclude_tuple_subclass(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, output = logger_and_output

        with pytest.raises(FileNotFoundError), logger.catch(exclude=(KeyError, OSError)):
            raise FileNotFoundError("nope")

        with logger.catch(exclude=(KeyError, OSError)):
            raise ValueError("logged")

        assert len(output) == 1
        assert "logged" in output[0]

    def test_default_return_value(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, _ = logger_and_output

        @logger.catch(default=-1)
        def parse_int(text: str) -> int:
            return int(text)

        assert parse_int("7") == 7
        assert parse_int("x") == -1

    def test_default_ignored_with_reraise(
        self, logger_and_output: tuple[Logger, list[str]]
    ) -> None:
        logger, _ = logger_and_output

        @logger.catch(default=-1, reraise=True)
        def risky() -> int:
            raise ValueError("x")

        with pytest.raises(ValueError):
            risky()

    def test_level_and_message(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, output = logger_and_output

        with logger.catch(level="WARNING", message="Handled"):
            raise ValueError("v")

        assert output[0].startswith("WARNING")
        assert "Handled: v" in output[0]

    def test_custom_level(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, output = logger_and_output
        logger.level("CATCHLVL", no=41, color="red")

        with logger.catch(level="CATCHLVL"):
            raise ValueError("v")

        assert output[0].startswith("CATCHLVL")

    def test_exception_braces_not_formatted(
        self, logger_and_output: tuple[Logger, list[str]]
    ) -> None:
        logger, output = logger_and_output

        with logger.catch():
            raise ValueError("bad {key}")

        assert "bad {key}" in output[0]


class TestCatchAsyncAndGenerators:
    """Test decorating coroutine and generator functions."""

    def test_async_function(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, output = logger_and_output

        @logger.catch(default="fallback")
        async def risky(fail: bool) -> str:
            await asyncio.sleep(0)
            if fail:
                raise ValueError("async boom")
            return "ok"

        assert asyncio.run(risky(False)) == "ok"
        assert asyncio.run(risky(True)) == "fallback"
        assert len(output) == 1
        assert "async boom" in output[0]

    def test_async_reraise(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, output = logger_and_output

        @logger.catch(reraise=True)
        async def risky() -> None:
            raise ValueError("async reraise")

        with pytest.raises(ValueError):
            asyncio.run(risky())
        assert len(output) == 1

    def test_generator_function(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, output = logger_and_output

        @logger.catch
        def numbers() -> Iterator[int]:
            yield 1
            yield 2
            raise ValueError("gen boom")

        def consumer() -> list[int]:
            return list(numbers())

        assert consumer() == [1, 2]
        assert len(output) == 1
        assert "gen boom" in output[0]
        assert "| consumer |" in output[0]

    def test_generator_return_value(self, logger_and_output: tuple[Logger, list[str]]) -> None:
        logger, _ = logger_and_output

        @logger.catch(default="dflt")
        def gen(fail: bool) -> Generator[int, None, str]:
            yield 1
            if fail:
                raise ValueError("x")
            return "done"

        def run(fail: bool) -> str:
            g = gen(fail)
            next(g)
            with pytest.raises(StopIteration) as exc_info:
                next(g)
            return str(exc_info.value.value)

        assert run(False) == "done"
        assert run(True) == "dflt"
