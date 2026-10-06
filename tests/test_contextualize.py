"""``contextualize()`` is context-local, with loguru's semantics.

Its values live in a ``contextvars.ContextVar`` (``logust._logust.CONTEXT_VAR``),
so concurrent asyncio tasks and threads never see each other's values, nested
blocks merge and restore, and every logger (bound or not, and the module-level
``logust.info``) reads the same variable. The Rust fast path reads the variable
too, so a plain ``logger.info("msg")`` inside a block stays in Rust.

Free-threaded safety: there is no shared mutable state. Each thread has its own
context, the stored dicts are never mutated after ``set()`` (a nested block
stores a new merged dict), and the Rust side only reads the variable and builds
a per-call merged context, so threads logging concurrently through one logger
need no lock.

Precedence (checked against loguru 0.7.3, ``Logger._log``:
``{**core.extra, **context.get(), **extra}`` then ``.update(kwargs)``):
``contextualize()`` < ``bind()`` < the message's own keyword arguments.
"""

from __future__ import annotations

import asyncio
import contextvars
import importlib
import json
import sys
import threading
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from typing import Any

import pytest

import logust
from logust import Logger, LogLevel
from logust._logust import CONTEXT_VAR, PyLogger

from .test_starlette_middleware import _load_starlette_module, _request


def _make(fast: bool = True) -> tuple[Logger, list[dict[str, Any]]]:
    """A logger with one ``serialize=True`` sink collecting records as dicts.

    JSON keeps the ``extra`` value types (a raw ``add_callback`` record renders
    them as text), so the assertions below can use plain Python values.
    """
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.remove()
    logger._fast_path = fast
    records: list[dict[str, Any]] = []

    def collect(line: str) -> None:
        record = json.loads(line)
        record.setdefault("extra", {})  # the JSON leaves an empty ``extra`` out
        records.append(record)

    logger.add(collect, serialize=True)
    return logger, records


def _extras(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """``message -> extra`` for records with distinct messages."""
    return {record["message"]: record["extra"] for record in records}


@pytest.fixture(params=[True, False], ids=["rust-fast-path", "python-path"])
def fast(request: pytest.FixtureRequest) -> bool:
    return bool(request.param)


@pytest.fixture(autouse=True)
def _no_context_leak() -> Generator[None, None, None]:
    """Every test starts and ends outside any ``contextualize()`` block."""
    assert CONTEXT_VAR.get(None) is None
    yield
    assert CONTEXT_VAR.get(None) is None


class TestBlocks:
    def test_values_apply_inside_and_vanish_outside(self, fast: bool) -> None:
        logger, records = _make(fast)

        with logger.contextualize(request_id="abc"):
            logger.info("inside")
        logger.info("outside")

        assert _extras(records) == {"inside": {"request_id": "abc"}, "outside": {}}

    def test_yields_the_logger(self) -> None:
        logger, _ = _make()

        with logger.contextualize(a=1) as yielded:
            assert yielded is logger

    def test_nested_blocks_merge_override_and_restore(self, fast: bool) -> None:
        logger, records = _make(fast)

        with logger.contextualize(a=1, b=1):
            logger.info("outer")
            with logger.contextualize(b=2, c=3):
                logger.info("inner")
            logger.info("outer again")
        logger.info("after")

        assert _extras(records) == {
            "outer": {"a": 1, "b": 1},
            "inner": {"a": 1, "b": 2, "c": 3},
            "outer again": {"a": 1, "b": 1},
            "after": {},
        }

    def test_exception_inside_block_restores(self, fast: bool) -> None:
        logger, records = _make(fast)

        with pytest.raises(ValueError, match="boom"), logger.contextualize(temp="x"):
            logger.info("before")
            raise ValueError("boom")
        logger.info("after")

        assert _extras(records) == {"before": {"temp": "x"}, "after": {}}
        assert CONTEXT_VAR.get(None) is None

    def test_empty_block_changes_nothing(self, fast: bool) -> None:
        logger, records = _make(fast)

        with logger.contextualize():
            logger.info("empty")

        assert _extras(records) == {"empty": {}}

    def test_stored_dict_is_not_mutated_by_nested_blocks(self) -> None:
        """Tasks that copied the outer context must keep seeing the outer values."""
        logger, _ = _make()

        with logger.contextualize(a=1):
            outer = CONTEXT_VAR.get()
            with logger.contextualize(b=2):
                assert CONTEXT_VAR.get() is not outer
            assert outer == {"a": 1}

    def test_exit_in_another_context_does_not_raise(self) -> None:
        """Entered in one ``contextvars.Context`` and exited in another: no error, no context."""
        logger, records = _make()
        block = logger.contextualize(x=1)

        contextvars.copy_context().run(block.__enter__)
        assert CONTEXT_VAR.get(None) is None
        block.__exit__(None, None, None)  # ``reset()`` fails: falls back to the previous value
        logger.info("after")

        assert _extras(records) == {"after": {}}
        assert CONTEXT_VAR.get(None) is None


class TestPrecedence:
    def test_bind_beats_contextualize(self, fast: bool) -> None:
        logger, records = _make(fast)

        with logger.contextualize(k="ctx", only_ctx=1):
            logger.bind(k="bound", only_bound=2).info("m")

        assert _extras(records) == {"m": {"k": "bound", "only_ctx": 1, "only_bound": 2}}

    def test_kwargs_beat_contextualize_and_bind(self, fast: bool) -> None:
        logger, records = _make(fast)

        with logger.contextualize(k="ctx", j="ctx"):
            logger.info("plain", k="kw")
            logger.bind(j="bound").info("bound", j="kw")

        assert _extras(records) == {
            "plain": {"k": "kw", "j": "ctx"},
            "bound": {"k": "ctx", "j": "kw"},
        }

    def test_bound_logger_created_before_the_block_sees_it(self, fast: bool) -> None:
        logger, records = _make(fast)
        bound = logger.bind(user="alice")

        with logger.contextualize(request="r1"):
            bound.info("in")
        bound.info("out")

        assert _extras(records) == {
            "in": {"user": "alice", "request": "r1"},
            "out": {"user": "alice"},
        }

    def test_block_opened_on_a_bound_logger_applies_to_the_root(self, fast: bool) -> None:
        logger, records = _make(fast)
        bound = logger.bind(user="alice")

        with bound.contextualize(request="r1"):
            logger.info("root")

        assert _extras(records) == {"root": {"request": "r1"}}

    def test_patcher_sees_and_can_hide_contextualized_values(self, fast: bool) -> None:
        logger, records = _make(fast)
        seen: list[dict[str, Any]] = []

        def patcher(record: dict[str, Any]) -> None:
            seen.append(dict(record["extra"]))
            record["extra"].pop("secret", None)

        patched = logger.bind(user="u").patch(patcher)
        with logger.contextualize(secret="s", request="r"):
            patched.info("m")

        assert seen == [{"secret": "s", "request": "r", "user": "u"}]
        extra = _extras(records)["m"]
        assert extra["request"] == "r" and extra["user"] == "u"
        assert extra["secret"] == ""  # removed keys are blanked, as for bound values

    def test_message_kwargs_used_by_placeholders_stay_out_of_extra(self, fast: bool) -> None:
        logger, records = _make(fast)

        with logger.contextualize(user="ctx"):
            logger.info("hello {name}", name="bob")

        assert _extras(records) == {"hello bob": {"user": "ctx"}}

    def test_custom_level_and_exception_paths(self, fast: bool) -> None:
        logger, records = _make(fast)
        logger.level("NOTICE", no=27)

        with logger.contextualize(ctx=1):
            logger.log("NOTICE", "custom")
            logger.log("INFO", "builtin by name")
            try:
                raise RuntimeError("x")
            except RuntimeError:
                logger.exception("exc")
            logger.opt(lazy=True).info("lazy {}", lambda: 1)

        assert _extras(records) == {
            "custom": {"ctx": 1},
            "builtin by name": {"ctx": 1},
            "exc": {"ctx": 1},
            "lazy 1": {"ctx": 1},
        }


class TestFastPath:
    def test_plain_calls_inside_a_block_stay_in_rust(self, monkeypatch: pytest.MonkeyPatch) -> None:
        logger, records = _make()

        def python_path(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("the Python path was taken")

        monkeypatch.setattr(Logger, "_log_with_level", python_path)
        with logger.contextualize(a=1):
            logger.info("fast")
            logger.log("INFO", "fast by name")

        assert _extras(records) == {"fast": {"a": 1}, "fast by name": {"a": 1}}

    def test_fast_and_python_paths_build_the_same_records(self) -> None:
        fast_logger, fast_records = _make(True)
        slow_logger, slow_records = _make(False)
        bound_fast = fast_logger.bind(k="bound", b=True)
        bound_slow = slow_logger.bind(k="bound", b=True)

        with fast_logger.contextualize(k="ctx", n=1, s="str", none=None, lst=[1, "a"]):
            fast_logger.info("plain")
            slow_logger.info("plain")
            bound_fast.info("bound")
            bound_slow.info("bound")

        keys = ("message", "extra", "level", "name", "function")
        assert [{k: r[k] for k in keys} for r in fast_records] == [
            {k: r[k] for k in keys} for r in slow_records
        ]
        assert _extras(fast_records)["bound"] == {
            "k": "bound",
            "b": True,
            "n": 1,
            "s": "str",
            "none": None,
            "lst": [1, "a"],
        }


class TestModuleLevel:
    def test_module_functions_see_the_context(self) -> None:
        records: list[dict[str, Any]] = []
        callback_id = logust.logger.add_callback(records.append)
        try:
            with logust.logger.contextualize(scope="module"):
                logust.info("mod")
                logust.logger.info("logger")
            logust.info("after")
        finally:
            logust.logger.remove_callback(callback_id)

        assert _extras(records) == {
            "mod": {"scope": "module"},
            "logger": {"scope": "module"},
            "after": {},
        }

    def test_separate_logger_instances_share_the_context(self, fast: bool) -> None:
        """Like loguru, the context is global to the process, not per logger."""
        first, first_records = _make(fast)
        second, second_records = _make(fast)

        with first.contextualize(shared=1):
            second.info("other")

        assert _extras(second_records) == {"other": {"shared": 1}}
        assert first_records == []


class TestConcurrency:
    def test_asyncio_tasks_do_not_see_each_other(self, fast: bool) -> None:
        logger, records = _make(fast)

        async def task(i: int) -> None:
            with logger.contextualize(task=i):
                logger.info(f"t{i}")
                await asyncio.sleep(0.001)
                logger.info(f"t{i}")
                await asyncio.sleep(0)
                logger.bind(step="end").info(f"t{i}")
            logger.info(f"done{i}")

        async def main() -> None:
            await asyncio.gather(*(task(i) for i in range(50)))

        asyncio.run(main())

        assert len(records) == 200
        for record in records:
            message, extra = record["message"], record["extra"]
            if message.startswith("done"):
                assert extra == {}, record
            else:
                assert extra["task"] == int(message[1:]), record

    def test_child_task_inherits_and_does_not_leak_back(self, fast: bool) -> None:
        logger, records = _make(fast)

        async def child() -> None:
            logger.info("child inherited")
            with logger.contextualize(child=True):
                logger.info("child own")
                await asyncio.sleep(0.001)

        async def main() -> None:
            with logger.contextualize(parent=1):
                task = asyncio.create_task(child())
                await asyncio.sleep(0.002)
                logger.info("parent while child runs")
                await task
                logger.info("parent after child")

        asyncio.run(main())

        assert _extras(records) == {
            "child inherited": {"parent": 1},
            "child own": {"parent": 1, "child": True},
            "parent while child runs": {"parent": 1},
            "parent after child": {"parent": 1},
        }

    def test_threads_do_not_see_each_other(self, fast: bool) -> None:
        logger, records = _make(fast)
        barrier = threading.Barrier(8)

        def worker(i: int) -> None:
            barrier.wait()
            for _ in range(100):
                with logger.contextualize(ctx=i):
                    logger.info(f"w{i}")
                    logger.info(f"w{i}")
                logger.info(f"out{i}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(records) == 8 * 100 * 3
        for record in records:
            message, extra = record["message"], record["extra"]
            if message.startswith("out"):
                assert extra == {}, record
            else:
                assert extra == {"ctx": int(message[1:])}, record

    def test_new_thread_follows_pythons_context_inheritance(self) -> None:
        """Threads inherit the context only when Python copies it for them.

        That is ``sys.flags.thread_inherit_context`` (Python 3.14+; on by
        default on free-threaded builds). ``contextvars.copy_context().run``
        always carries it over.
        """
        logger, records = _make()
        inherits = bool(getattr(sys.flags, "thread_inherit_context", 0))

        def plain() -> None:
            logger.info("plain thread")

        def copied() -> None:
            logger.info("copied context")

        with logger.contextualize(req="r"):
            thread = threading.Thread(target=plain)
            thread.start()
            thread.join()
            context = contextvars.copy_context()
            thread = threading.Thread(target=context.run, args=(copied,))
            thread.start()
            thread.join()

        extras = _extras(records)
        assert extras["plain thread"] == ({"req": "r"} if inherits else {})
        assert extras["copied context"] == {"req": "r"}


class TestGenerators:
    def test_generator_block_follows_contextvar_semantics(self) -> None:
        """A generator runs in its caller's context, so a block left open across a
        ``yield`` is visible to the caller until the generator resumes and exits it
        (the same as loguru).
        """
        logger, records = _make()

        def gen() -> Generator[int, None, None]:
            with logger.contextualize(gen=1):
                logger.info("gen first")
                yield 1
                logger.info("gen second")
                yield 2

        iterator = gen()
        next(iterator)
        logger.info("caller between")
        next(iterator)
        with pytest.raises(StopIteration):
            next(iterator)
        logger.info("caller after")

        assert _extras(records) == {
            "gen first": {"gen": 1},
            "caller between": {"gen": 1},
            "gen second": {"gen": 1},
            "caller after": {},
        }

    def test_generator_consumed_inside_a_block(self, fast: bool) -> None:
        logger, records = _make(fast)

        def items() -> Generator[int, None, None]:
            for i in range(3):
                logger.info(f"item{i}")
                yield i

        with logger.contextualize(batch="b1"):
            assert list(items()) == [0, 1, 2]

        assert all(extra == {"batch": "b1"} for extra in _extras(records).values())

    def test_async_generator_in_one_task(self) -> None:
        logger, records = _make()

        async def agen() -> AsyncGenerator[int, None]:
            with logger.contextualize(ag=1):
                logger.info("agen first")
                yield 1
                await asyncio.sleep(0.001)
                logger.info("agen second")
                yield 2

        async def main() -> None:
            async for _ in agen():
                logger.info("consumer")
            logger.info("after")

        asyncio.run(main())

        assert [(r["message"], r["extra"]) for r in records] == [
            ("agen first", {"ag": 1}),
            ("consumer", {"ag": 1}),
            ("agen second", {"ag": 1}),
            ("consumer", {"ag": 1}),
            ("after", {}),
        ]

    def test_async_generator_closed_by_another_task_does_not_raise(self) -> None:
        logger, records = _make()

        async def agen() -> AsyncGenerator[int, None]:
            with logger.contextualize(ag=1):
                yield 1
                yield 2

        async def main() -> None:
            iterator = agen()
            await iterator.__anext__()
            await asyncio.create_task(iterator.aclose())
            logger.info("closed elsewhere")
            # The var was set in this task's context and could only be reset from
            # the closing task (contextvars semantics); clear it explicitly.
            CONTEXT_VAR.set(None)
            logger.info("after")

        asyncio.run(main())

        assert _extras(records) == {"closed elsewhere": {"ag": 1}, "after": {}}


class TestStarletteMiddleware:
    def test_concurrent_requests_keep_their_own_request_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """30 concurrent requests through the middleware: every handler line carries
        its own request's id and path (stubbed Starlette, see test_starlette_middleware).
        """
        module = _load_starlette_module(monkeypatch)
        logger, records = _make()
        middleware = module.RequestLoggerMiddleware(object(), logger=logger)

        async def call_next(request: Any) -> Any:
            await asyncio.sleep(0.001)
            logger.info(f"handler {request.headers['x-request-id']}")
            await asyncio.sleep(0.001)
            logger.bind(stage="end").info(f"handler {request.headers['x-request-id']}")
            return SimpleNamespace(status_code=200)

        async def main() -> None:
            await asyncio.gather(
                *(
                    middleware._log_request(_request(request_id=f"req-{i}"), call_next)
                    for i in range(30)
                )
            )

        asyncio.run(main())

        handler_lines = [r for r in records if r["message"].startswith("handler ")]
        assert len(handler_lines) == 60
        for record in handler_lines:
            assert record["extra"]["request_id"] == record["message"].split()[1], record
            assert record["extra"]["path"] == "/items"
        # Start/finish lines are contextualized too
        for record in records:
            assert record["extra"]["request_id"].startswith("req-"), record
        assert CONTEXT_VAR.get(None) is None

    def test_real_starlette_concurrent_requests(self) -> None:
        pytest.importorskip("starlette")
        httpx = pytest.importorskip("httpx")
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        sys.modules.pop("logust.contrib.starlette", None)  # other tests load a stubbed copy
        module = importlib.import_module("logust.contrib.starlette")
        logger, records = _make()

        async def handler(request: Request) -> PlainTextResponse:
            await asyncio.sleep(0.001)
            logger.info(f"handler {request.headers['x-request-id']}")
            await asyncio.sleep(0.001)
            return PlainTextResponse(module.get_request_id())

        app = Starlette(routes=[Route("/items/{n}", handler)])
        app.add_middleware(module.RequestLoggerMiddleware, logger=logger)

        async def main() -> list[Any]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await asyncio.gather(
                    *(
                        client.get(f"/items/{i}", headers={"x-request-id": f"req-{i}"})
                        for i in range(30)
                    )
                )

        responses = asyncio.run(main())

        assert [r.text for r in responses] == [f"req-{i}" for i in range(30)]
        handler_lines = [r for r in records if r["message"].startswith("handler ")]
        assert len(handler_lines) == 30
        for record in handler_lines:
            request_id = record["message"].split()[1]
            assert record["extra"]["request_id"] == request_id, record
            assert record["extra"]["path"] == f"/items/{request_id[4:]}"
        assert len([r for r in records if r["message"].startswith("Request started")]) == 30
