"""The Rust fast path (``PyLogger.log_fast``) builds the same records as the Python path.

``Logger.info("msg")`` and the other level methods hand plain calls to Rust,
which reads the caller frame, thread and process itself. Every test here logs
the same message through a logger on the fast path and one forced onto the
Python path (``_fast_path = False``) from the same call site and compares the
records field by field.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest

from logust import CallerInfo, CollectOptions, Logger, LogLevel
from logust._logust import PyLogger

FORMAT = (
    "{name}|{function}|{line}|{file.path}|{thread.name}|{thread.id}"
    "|{process.name}|{process.id}|{level}|{message}|{extra}"
)
RECORD_KEYS = (
    "name",
    "function",
    "line",
    "file",
    "module",
    "thread_name",
    "thread_id",
    "process_name",
    "process_id",
    "level",
    "level_no",
    "message",
    "extra",
    "exception",
)


class Pair:
    """A fast-path logger and a Python-path logger with identical handlers."""

    def __init__(self, **add_kwargs: Any) -> None:
        self.fast_out: list[str] = []
        self.slow_out: list[str] = []
        self.fast = self._make(True, self.fast_out, add_kwargs)
        self.slow = self._make(False, self.slow_out, add_kwargs)

    @staticmethod
    def _make(fast: bool, out: list[str], add_kwargs: dict[str, Any]) -> Logger:
        logger = Logger(PyLogger(LogLevel.Trace))
        logger.remove()
        logger._fast_path = fast
        kwargs = {"format": FORMAT, "level": "TRACE", **add_kwargs}
        logger.add(out.append, **kwargs)
        return logger

    def run(self, emit: Callable[[Logger], Any]) -> None:
        """Log through both loggers; the fast one must not use the Python helpers."""
        with (
            patch("logust._logger._get_caller_info", side_effect=AssertionError("python path")),
            patch("logust._logger._get_thread_info", side_effect=AssertionError("python path")),
            patch("logust._logger._get_process_info", side_effect=AssertionError("python path")),
        ):
            emit(self.fast)
        emit(self.slow)
        assert self.fast_out, "nothing logged"
        assert self.fast_out == self.slow_out
        self.fast_out.clear()
        self.slow_out.clear()

    def run_either(self, emit: Callable[[Logger], Any]) -> None:
        """Compare outputs where the fast logger may legitimately use the Python path."""
        emit(self.fast)
        emit(self.slow)
        assert self.fast_out, "nothing logged"
        assert self.fast_out == self.slow_out
        self.fast_out.clear()
        self.slow_out.clear()


@pytest.fixture
def pair() -> Pair:
    return Pair()


def module_level_function(logger: Logger) -> None:
    logger.info("from a module-level function")


class TestCallSites:
    def test_direct_call(self, pair: Pair) -> None:
        pair.run(lambda logger: logger.info("direct"))
        assert "|test_direct_call|" not in pair.fast_out  # cleared by run()

    def test_every_level_method(self, pair: Pair) -> None:
        def emit(logger: Logger) -> None:
            logger.trace("t")
            logger.debug("d")
            logger.info("i")
            logger.success("s")
            logger.warning("w")
            logger.error("e")
            logger.fail("f")
            logger.critical("c")

        pair.run(emit)

    def test_module_level_function(self, pair: Pair) -> None:
        pair.run(module_level_function)

    def test_nested_function(self, pair: Pair) -> None:
        def emit(logger: Logger) -> None:
            def inner() -> None:
                logger.info("nested")

            inner()

        pair.run(emit)

    def test_lambda(self, pair: Pair) -> None:
        pair.run(lambda logger: (lambda: logger.info("lambda"))())

    def test_comprehensions(self, pair: Pair) -> None:
        def emit(logger: Logger) -> None:
            [logger.info("list comp") for _ in range(1)]
            {logger.info("set comp") for _ in range(1)}
            next(logger.info("generator expression") for _ in range(1))

        pair.run(emit)

    def test_generator_function(self, pair: Pair) -> None:
        def emit(logger: Logger) -> None:
            def gen() -> Any:
                logger.info("before yield")
                yield 1
                logger.info("after yield")

            list(gen())

        pair.run(emit)

    def test_async_function(self, pair: Pair) -> None:
        def emit(logger: Logger) -> None:
            async def coro() -> None:
                logger.info("before await")
                await asyncio.sleep(0)
                logger.info("after await")

            asyncio.run(coro())

        pair.run(emit)

    def test_exec_with_module_name(self, pair: Pair) -> None:
        code = compile("logger.info('exec')\n", "<fast-path-test>", "exec")
        pair.run(lambda logger: exec(code, {"__name__": "exec_module", "logger": logger}))
        pair.run(lambda logger: exec(code, {"logger": logger}))  # name falls back to the file
        pair.run(lambda logger: exec(code, {"__name__": None, "logger": logger}))

    def test_exec_with_non_str_module_name_raises_like_python_path(self, pair: Pair) -> None:
        code = compile("logger.info('exec')\n", "<fast-path-test>", "exec")
        for logger in (pair.fast, pair.slow):
            with pytest.raises(TypeError):
                exec(code, {"__name__": 5, "logger": logger})
        assert pair.fast_out == pair.slow_out == []

    def test_depth_past_the_top_of_the_stack(self, pair: Pair) -> None:
        pair.run(lambda logger: logger.info("too deep", _depth=10_000))

    def test_explicit_depth_from_a_wrapper(self, pair: Pair) -> None:
        def wrapper(logger: Logger, message: str) -> None:
            logger.info(message, _depth=1)

        def emit(logger: Logger) -> None:
            wrapper(logger, "through wrapper")

        pair.run(emit)

    def test_opt_depth(self, pair: Pair) -> None:
        def emit(logger: Logger) -> None:
            def inner() -> None:
                logger.opt().info("opt depth 0")
                logger.opt(depth=1).info("opt depth 1")
                logger.opt(lazy=True).info("lazy {}", lambda: "value")

            inner()

        pair.run_either(emit)

    def test_log_with_builtin_level(self, pair: Pair) -> None:
        def emit(logger: Logger) -> None:
            logger.log("INFO", "by name")
            logger.log("warning", "lower-case name")
            logger.log(20, "by number")

        pair.run(emit)

    def test_log_with_custom_level(self, pair: Pair) -> None:
        pair.fast.level("NOTICE", no=27, color="cyan")

        def emit(logger: Logger) -> None:
            logger.log("NOTICE", "custom level")

        pair.run_either(emit)

    def test_bound_logger(self, pair: Pair) -> None:
        def emit(logger: Logger) -> None:
            logger.bind(user="alice", attempt=2).info("bound")
            with logger.contextualize(request="r1"):
                logger.info("contextualized")

        pair.run(emit)

    def test_exception_and_catch(self, pair: Pair) -> None:
        def emit(logger: Logger) -> None:
            try:
                raise ValueError("boom")
            except ValueError:
                logger.exception("caught")
            with logger.catch(message="in with"):
                raise RuntimeError("x")

            @logger.catch(message="decorated")
            def fails() -> None:
                raise KeyError("k")

            fails()

        pair.run_either(emit)

    def test_message_coercion(self, pair: Pair) -> None:
        class Shouty(str):
            def __str__(self) -> str:
                return self.upper()

        def emit(logger: Logger) -> None:
            logger.info(42)  # type: ignore[arg-type]
            logger.info(Shouty("subclass"))
            logger.info("<red>markup</red>")

        pair.run(emit)

    def test_other_thread(self, pair: Pair) -> None:
        def emit(logger: Logger) -> None:
            thread = threading.Thread(target=logger.info, args=("worker",), name="fast-path-worker")
            thread.start()
            thread.join()

        pair.run(emit)
        assert pair.fast_out == []


class TestSlowPathTriggers:
    """Call shapes the fast path refuses still produce identical records."""

    def test_args_and_kwargs(self, pair: Pair) -> None:
        def emit(logger: Logger) -> None:
            logger.info("{} items", 3)
            logger.info("{n} items", n=4)
            logger.info("user {user}", user="bob", extra_key=1)

        pair.run_either(emit)

    def test_patcher(self, pair: Pair) -> None:
        def add(record: dict[str, Any]) -> None:
            record["extra"]["patched"] = True

        def emit(logger: Logger) -> None:
            logger.patch(add).info("patched")

        pair.run_either(emit)

    def test_module_activation_rules(self, pair: Pair) -> None:
        for logger in (pair.fast, pair.slow):
            logger.disable("some.other.module")

        def emit(logger: Logger) -> None:
            logger.info("still enabled")

        pair.run_either(emit)

        for logger in (pair.fast, pair.slow):
            logger.disable(__name__)
        pair.fast.info("dropped")
        pair.slow.info("dropped")
        assert pair.fast_out == pair.slow_out == []


class TestCollectOptions:
    def test_caller_false_leaves_caller_empty(self) -> None:
        pair = Pair(collect=CollectOptions(caller=False))
        pair.run(lambda logger: logger.info("no caller"))

    def test_fixed_caller_uses_the_python_path(self) -> None:
        fixed = CallerInfo(name="fixed", function="fn", line=7, file="/tmp/fixed.py")
        pair = Pair(collect=CollectOptions(caller=fixed))
        pair.run_either(lambda logger: logger.info("fixed caller"))
        pair.fast.info("fixed caller")
        assert pair.fast_out[0].startswith("fixed|fn|7|/tmp/fixed.py|")

    def test_requirements_follow_handler_changes(self) -> None:
        pair = Pair()
        fast_file: list[str] = []
        slow_file: list[str] = []
        pair.fast.add(fast_file.append, format="{message}", level="ERROR")
        pair.slow.add(slow_file.append, format="{message}", level="ERROR")
        pair.run(lambda logger: logger.error("two sinks"))
        assert fast_file == slow_file == ["two sinks"]
        # Removing the only caller-aware sink turns caller collection off again
        pair.fast.remove()
        pair.slow.remove()
        pair.fast.add(pair.fast_out.append, format="{message}")
        pair.slow.add(pair.slow_out.append, format="{message}")
        pair.run(lambda logger: logger.info("message only"))


class TestRawRecords:
    def test_callback_records_match(self) -> None:
        fast_records: list[dict[str, Any]] = []
        slow_records: list[dict[str, Any]] = []
        fast = Logger(PyLogger(LogLevel.Trace))
        fast.remove()
        slow = Logger(PyLogger(LogLevel.Trace))
        slow.remove()
        slow._fast_path = False
        fast.add_callback(fast_records.append)
        slow.add_callback(slow_records.append)

        def emit(logger: Logger) -> None:
            logger.bind(k="v").warning("raw record")

        with patch("logust._logger._get_caller_info", side_effect=AssertionError("python path")):
            emit(fast)
        emit(slow)

        assert len(fast_records) == len(slow_records) == 1
        for key in RECORD_KEYS:
            assert fast_records[0][key] == slow_records[0][key], key
        assert fast_records[0]["function"] == "emit"
        assert fast_records[0]["thread_id"] == threading.get_ident()

    def test_filtered_sink_sees_the_same_record(self) -> None:
        seen: list[tuple[str, str, int]] = []

        def keep(record: dict[str, Any]) -> bool:
            seen.append((record["name"], record["function"], record["line"]))
            return True

        pair = Pair(filter=keep)
        pair.run_either(lambda logger: logger.info("filtered"))
        assert len(seen) == 2 and seen[0] == seen[1]
