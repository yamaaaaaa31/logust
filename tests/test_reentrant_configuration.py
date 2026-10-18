"""Configuration changes must not deadlock callbacks, filters, or finalizers.

Run in bounded subprocesses so a lock regression cannot hang the test suite.
Each record keeps its original destinations; changes apply to later records.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCENARIOS = {
    "concurrent_add": """
        import threading, time
        entered = threading.Event()
        errors = []
        def sink(message):
            entered.set()
            time.sleep(0.1)
        logger.add(sink, format="{message}")
        def worker():
            try:
                emit("first")
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=worker)
        thread.start()
        assert entered.wait(2)
        logger.add(path, format="{message}")
        thread.join(2)
        assert not thread.is_alive()
        assert not errors
        emit("second")
        logger.complete()
        assert path.read_text() == "second\\n"
    """,
    "filter_remove": """
        def keep(record):
            logger.remove(handler_id)
            return True
        handler_id = logger.add(path, format="{message}", filter=keep, catch=False)
        emit("first")
        emit("second")
        assert path.read_text() == "first\\n"
    """,
    "formatted_sink_remove": """
        seen = []
        def sink(message):
            logger.remove(handler_id)
            seen.append(message)
        handler_id = logger.add(sink, format="{message}", catch=False)
        emit("first")
        emit("second")
        assert seen == ["first"]
    """,
    "serialized_sink_remove": """
        import json
        seen = []
        def sink(message):
            logger.remove(handler_id)
            seen.append(json.loads(message)["message"])
        handler_id = logger.add(sink, serialize=True, catch=False)
        emit("first")
        emit("second")
        assert seen == ["first"]
    """,
    "raw_callback_remove": """
        seen = []
        def callback(record):
            logger.remove_callback(callback_id)
            seen.append(record["message"])
        callback_id = logger.add_callback(callback)
        emit("first")
        emit("second")
        assert seen == ["first"]
    """,
    "remove_all_keeps_current_record": """
        seen = []
        def callback(record):
            seen.append("raw:" + record["message"])
            logger.remove()
        logger.add_callback(callback)
        logger.add(lambda message: seen.append("sink:" + message), format="{message}")
        logger.add(path, format="{message}")
        emit("first")
        emit("second")
        assert seen == ["raw:first", "sink:first"]
        assert path.read_text() == "first\\n"
    """,
    "add_keeps_current_record": """
        seen = []
        added = False
        def callback(record):
            global added
            if not added:
                added = True
                logger.add(lambda message: seen.append("late:" + message), format="{message}")
                logger.add(path, format="{message}")
        logger.add_callback(callback)
        logger.add(lambda message: seen.append("early:" + message), format="{message}")
        emit("first")
        emit("second")
        logger.complete()
        assert seen == ["early:first", "early:second", "late:second"]
        assert path.read_text() == "second\\n"
    """,
    "filter_error_after_mutation": """
        def reject(record):
            logger.remove(bad_id)
            raise ValueError("filter failed")
        bad_id = logger.add(path.with_name("bad.log"), filter=reject, catch=False)
        logger.add(path, format="{message}")
        try:
            emit("first")
        except ValueError as error:
            assert str(error) == "filter failed"
        else:
            raise AssertionError("filter exception was swallowed")
        emit("second")
        logger.complete()
        assert path.read_text() == "first\\nsecond\\n"
    """,
    "sink_error_after_mutation": """
        def sink(message):
            logger.remove(bad_id)
            raise ValueError("sink failed")
        bad_id = logger.add(sink, catch=False)
        logger.add(path, format="{message}")
        try:
            emit("first")
        except ValueError as error:
            assert str(error) == "sink failed"
        else:
            raise AssertionError("sink exception was swallowed")
        emit("second")
        logger.complete()
        assert path.read_text() == "first\\nsecond\\n"
    """,
    "filter_finalizer": """
        finalized = []
        class Filter:
            def __call__(self, record):
                return True
            def __del__(self):
                logger.add(path.with_name("finalizer.log"), format="{message}")
                finalized.append(True)
        handler_id = logger.add(path, filter=Filter())
        logger.remove(handler_id)
        assert finalized == [True]
        emit("after")
        logger.complete()
        assert path.with_name("finalizer.log").read_text() == "after\\n"
    """,
    "callback_finalizer": """
        finalized = []
        class Callback:
            def __call__(self, record):
                pass
            def __del__(self):
                logger.add(path, format="{message}")
                finalized.append(True)
        callback_id = logger.add_callback(Callback())
        logger.remove_callback(callback_id)
        assert finalized == [True]
        emit("after")
        logger.complete()
        assert path.read_text() == "after\\n"
    """,
    "batch_callback_finalizer": """
        finalized = []
        seen = []
        new_ids = []
        class Callback:
            def __call__(self, record):
                pass
            def __del__(self):
                new_ids.append(logger.add(seen.append, format="{message}"))
                finalized.append(True)
        logger.add_callback(Callback())
        logger.remove()
        assert finalized == [True]
        emit("after")
        assert seen == ["after"]
        assert logger.remove(new_ids[0])
        emit("removed")
        assert seen == ["after"]
    """,
    "remove_all_filter_finalizer": """
        seen = []
        new_ids = []
        class Filter:
            def __call__(self, record):
                return True
            def __del__(self):
                new_ids.append(logger.add(seen.append, format="{message}"))
        logger.add(path, filter=Filter())
        logger.remove()
        emit("after")
        assert seen == ["after"]
        assert logger.remove(new_ids[0])
        emit("removed")
        assert seen == ["after"]
    """,
    "complete_inside_callback": """
        logger.add(path, format="{message}", enqueue=True)
        logger.add_callback(lambda record: logger.complete())
        emit("first")
        logger.complete()
        assert path.read_text() == "first\\n"
    """,
    "exception_variants_descriptor": """
        class ExceptionText(str):
            @property
            def variants(self):
                logger.add(path.with_name("added.log"), format="{message}")
                return (None, None, None, None)
        logger.add(path, format="{message}")
        method = logger._inner.log if sys.argv[2] == "custom" else logger._inner.info
        args = ("CONFIG_SNAPSHOT", "first") if sys.argv[2] == "custom" else ("first",)
        method(*args, exception=ExceptionText("traceback"))
        logger.complete()
        assert path.read_text().startswith("first")
        assert path.with_name("added.log").read_text().startswith("first")
    """,
    "enable_stream_detection": """
        import builtins, os, types
        os.environ.pop("NO_COLOR", None)
        os.environ.pop("FORCE_COLOR", None)
        builtins.__IPYTHON__ = True
        checked = []
        class StreamMeta(type):
            def __instancecheck__(cls, instance):
                logger.add(path, format="{message}")
                checked.append(True)
                return False
        class OutStream(metaclass=StreamMeta):
            pass
        sys.modules["ipykernel.iostream"] = types.SimpleNamespace(OutStream=OutStream)
        logger.enable()
        assert checked == [True]
        assert logger._inner.handler_count == 2
        emit("first")
        logger.complete()
        assert path.read_text() == "first\\n"
    """,
    "exception_variant_snapshot": """
        seen = []
        changed = []
        target = [None]
        def change_variant(record):
            if not changed:
                assert logger._inner.set_exception_variant(target[0], 2)
                changed.append(True)
        logger.add_callback(change_variant)
        target[0] = logger.add(seen.append, format="{message}|{exception}")
        class ExceptionText(str):
            variants = (None, None, "DIAG", None)
        for message in ("first", "second"):
            if sys.argv[2] == "custom":
                logger.log("CONFIG_SNAPSHOT", message, exception=ExceptionText("BASE"))
            else:
                logger.info(message, exception=ExceptionText("BASE"))
        assert seen == ["first|BASE", "second|DIAG"], seen
    """,
    "console_level_snapshot": """
        logger.enable(level="INFO")
        changed = []
        def change_level(record):
            if not changed:
                logger.set_level("ERROR")
                changed.append(True)
        logger.add_callback(change_level)
        emit("COW_FIRST")
        emit("COW_SECOND")
        logger.error("COW_THIRD")
    """,
}


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("custom_level", [False, True], ids=["builtin", "custom"])
def test_configuration_during_dispatch(tmp_path: Path, scenario: str, custom_level: bool) -> None:
    setup = """
        import sys
        from pathlib import Path
        from logust import logger
        logger.remove()
        path = Path(sys.argv[1])
        logger.level("CONFIG_SNAPSHOT", no=23)
        def emit(message):
            if sys.argv[2] == "custom":
                logger.log("CONFIG_SNAPSHOT", message)
            else:
                logger.info(message)
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(setup) + textwrap.dedent(SCENARIOS[scenario]),
            str(tmp_path / "app.log"),
            "custom" if custom_level else "builtin",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    if scenario == "console_level_snapshot":
        assert "COW_FIRST" in result.stderr
        assert "COW_SECOND" not in result.stderr
        assert "COW_THIRD" in result.stderr
