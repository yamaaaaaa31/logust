"""Tests for loguru-style per-module ``enable(name)`` / ``disable(name)``."""

from __future__ import annotations

import importlib
import logging
import sys
import textwrap
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

import logust
from logust import Logger, LogLevel
from logust._logust import PyLogger
from logust.contrib.logging_handler import InterceptHandler

THIS_MODULE = __name__


@pytest.fixture
def capture() -> Generator[tuple[Logger, list[str]], None, None]:
    """A fresh logger (no console) whose messages are collected as ``name|message``."""
    logger = Logger(PyLogger(LogLevel.Trace))
    logger.disable()
    messages: list[str] = []
    logger.add(lambda msg: messages.append(msg.rstrip("\n")), format="{name}|{message}")
    yield logger, messages
    logger.remove()


def _messages(messages: list[str]) -> list[str]:
    return [m.split("|", 1)[1] for m in messages]


def _write_package(root: Path, name: str) -> None:
    """Create ``name`` with a submodule; both log through the global logust logger."""
    pkg = root / name
    pkg.mkdir()
    body = textwrap.dedent(
        """
        from logust import logger


        def work(tag):
            logger.info("{} from {}", tag, __name__)
            logger.opt(lazy=True).debug("lazy {}", lambda: tag)
            logger.log("WARNING", "log {}", tag)
        """
    )
    (pkg / "__init__.py").write_text(body, encoding="utf-8")
    (pkg / "sub.py").write_text(body, encoding="utf-8")


class TestPrefixSemantics:
    def test_disable_module_drops_its_messages(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        logger.disable(THIS_MODULE)
        logger.info("hidden")
        logger.enable(THIS_MODULE)
        logger.info("shown")
        assert messages == [f"{THIS_MODULE}|shown"]

    def test_parent_package_disables_submodules(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        parent = THIS_MODULE.rsplit(".", 1)[0]  # "tests"
        logger.disable(parent)
        logger.info("hidden")
        assert messages == []

    def test_prefix_matches_dotted_path_only(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        # "tests.test_module" is a string prefix but not a dotted parent
        logger.disable(THIS_MODULE[:-3])
        logger.info("shown")
        assert _messages(messages) == ["shown"]

    def test_other_module_unaffected(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        logger.disable("some_other_lib")
        logger.info("shown")
        assert _messages(messages) == ["shown"]

    def test_most_specific_rule_wins(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        parent = THIS_MODULE.rsplit(".", 1)[0]
        logger.disable(parent)
        logger.enable(THIS_MODULE)
        logger.info("child enabled")
        logger.disable(THIS_MODULE)
        logger.enable(parent)  # Supersedes the rules for its submodules
        logger.info("parent enabled")
        assert _messages(messages) == ["child enabled", "parent enabled"]

    def test_empty_name_means_all_modules(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        logger.disable("")
        logger.info("hidden")
        logger.enable(THIS_MODULE)
        logger.info("re-enabled module")
        logger.disable(THIS_MODULE)
        logger.enable("")  # Clears every rule
        logger.info("all enabled")
        assert _messages(messages) == ["re-enabled module", "all enabled"]

    def test_rules_take_effect_after_cached_decision(
        self, capture: tuple[Logger, list[str]]
    ) -> None:
        logger, messages = capture
        logger.disable("unrelated")
        logger.info("one")  # Caches "enabled" for this module
        logger.disable(THIS_MODULE)
        logger.info("two")
        assert _messages(messages) == ["one"]

    def test_disable_rejects_non_string(self, capture: tuple[Logger, list[str]]) -> None:
        logger, _ = capture
        with pytest.raises(TypeError):
            logger.disable(42)  # type: ignore[arg-type]

    def test_internal_rules_are_compact(self) -> None:
        logger = Logger(PyLogger(LogLevel.Trace))
        logger.disable()
        logger.enable("a")  # Already enabled: no rule
        assert logger._activation.rules == ()
        logger.disable("a")
        logger.disable("a.b")  # Already disabled by parent: no rule
        logger.enable("a.b.c")
        assert logger._activation.rules == (("a.b.c.", True), ("a.", False))
        logger.enable("a")
        assert logger._activation.rules == ()


class TestLevelInteraction:
    def test_level_names_keep_console_behavior(self, capture: tuple[Logger, list[str]]) -> None:
        logger, _ = capture
        for value in ("INFO", "info", "Warning", LogLevel.Debug):
            logger.enable(value)
            assert logger.is_enabled()
            logger.disable()
            assert not logger.is_enabled()
        logger.enable(level="ERROR")
        assert logger.is_enabled()
        logger.disable()
        assert logger._activation.rules == ()

    def test_module_name_does_not_touch_console(self, capture: tuple[Logger, list[str]]) -> None:
        logger, _ = capture
        logger.enable("mylib")
        assert not logger.is_enabled()

    def test_module_name_with_level_is_an_error(self, capture: tuple[Logger, list[str]]) -> None:
        logger, _ = capture
        with pytest.raises(TypeError):
            logger.enable("mylib", level="INFO")

    def test_min_level_check_still_first(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        logger.remove()
        logger.add(lambda msg: messages.append(msg), level="INFO", format="{message}")
        logger.disable("other")
        logger.debug("filtered by level")
        logger.info("shown")
        assert [m.strip() for m in messages] == ["shown"]


class TestAllEntryPoints:
    def test_bound_and_patched_loggers_share_rules(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        bound = logger.bind(user="x")
        patched = logger.patch(lambda r: None)
        logger.disable(THIS_MODULE)
        bound.info("hidden")
        patched.info("hidden")
        bound.enable(THIS_MODULE)
        logger.info("shown")
        assert _messages(messages) == ["shown"]

    def test_log_exception_and_opt(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        logger.level("NOTICE_ME", no=22)
        logger.disable(THIS_MODULE)
        calls: list[int] = []

        def expensive() -> int:
            calls.append(1)
            return 1

        logger.log("INFO", "hidden")
        logger.log("NOTICE_ME", "hidden")
        logger.log(20, "hidden")
        logger.opt().info("hidden")
        logger.opt(lazy=True).info("hidden {}", expensive)
        logger.opt(depth=0).log("NOTICE_ME", "hidden")
        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("hidden")
            logger.opt(exception=True).error("hidden")
        assert messages == []
        assert calls == []

    def test_catch_respects_rules(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        logger.disable(THIS_MODULE)

        @logger.catch
        def fails() -> None:
            raise ValueError("boom")

        fails()
        with logger.catch():
            raise ValueError("boom")
        assert messages == []

    def test_opt_depth_uses_outer_module(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        logger.disable(THIS_MODULE)
        # A wrapper defined in another module logging with depth=1 attributes
        # the record to its caller (this module), which is disabled.
        namespace: dict[str, Any] = {"__name__": "wrapper_mod"}
        exec(
            "def wrap(lg, m):\n    lg.opt(depth=1).info(m)\n    lg.info(m + ' direct')\n",
            namespace,
        )
        namespace["wrap"](logger, "msg")
        assert messages == ["wrapper_mod|msg direct"]

    def test_configure_activation(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        parent = THIS_MODULE.rsplit(".", 1)[0]
        logger.configure(activation=[(parent, False), (THIS_MODULE, True)])
        logger.info("shown")
        logger.configure(activation=[("", False)])
        logger.info("hidden")
        assert _messages(messages) == ["shown"]


class TestModuleLevelProxies:
    def test_logust_enable_disable(self) -> None:
        messages: list[str] = []
        handler_id = logust.logger.add(lambda msg: messages.append(msg), format="{message}")
        try:
            logust.disable(THIS_MODULE)
            logust.info("hidden")
            logust.enable(THIS_MODULE)
            logust.info("shown")
        finally:
            logust.logger.remove(handler_id)
            logust.enable("")
        assert [m.strip() for m in messages] == ["shown"]


class TestLibraryScenario:
    def test_library_disables_itself_and_user_reenables(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        name = "logust_test_mylib"
        _write_package(tmp_path, name)
        monkeypatch.syspath_prepend(str(tmp_path))
        messages: list[str] = []
        handler_id = logust.logger.add(
            lambda msg: messages.append(msg.rstrip("\n")),
            level="TRACE",
            format="{name}|{message}",
        )
        try:
            lib = importlib.import_module(name)
            sub = importlib.import_module(f"{name}.sub")
            # The library silences itself at import time, as loguru recommends
            logust.logger.disable(name)
            lib.work("a")
            sub.work("b")
            assert messages == []

            # The application opts back in to one submodule
            logust.logger.enable(f"{name}.sub")
            lib.work("c")
            sub.work("d")
            assert messages == [
                f"{name}.sub|d from {name}.sub",
                f"{name}.sub|lazy d",
                f"{name}.sub|log d",
            ]

            messages.clear()
            logust.logger.enable(name)
            lib.work("e")
            assert len(messages) == 3
        finally:
            logust.logger.remove(handler_id)
            logust.logger.enable("")
            for mod in (name, f"{name}.sub"):
                sys.modules.pop(mod, None)


class TestInterceptHandler:
    def test_stdlib_logger_name_is_matched(self, capture: tuple[Logger, list[str]]) -> None:
        logger, messages = capture
        handler = InterceptHandler(logger)
        std = logging.getLogger("thirdparty.client")
        std.propagate = False
        std.addHandler(handler)
        std.setLevel(logging.DEBUG)
        try:
            logger.disable("thirdparty")
            std.info("hidden")
            logger.enable("thirdparty.client")
            std.info("shown")
        finally:
            std.removeHandler(handler)
        assert _messages(messages) == ["shown"]
