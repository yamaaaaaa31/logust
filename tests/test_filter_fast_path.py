"""Filter fast path: eligible handlers only use GIL and run filters."""

from __future__ import annotations

from pathlib import Path

from logust import Logger, LogLevel
from logust._logust import PyLogger


def _fresh_logger() -> Logger:
    inner = PyLogger(LogLevel.Trace)
    logger = Logger(inner)
    logger.remove()
    return logger


class TestFilterFastPathBuiltin:
    """INFO logs must not run filters on higher-threshold handlers."""

    def test_info_does_not_invoke_error_handler_filter(self, tmp_path: Path) -> None:
        """ERROR-level filtered handler: filter not called for INFO; called for ERROR."""
        logger = _fresh_logger()
        info_log = tmp_path / "info.log"
        err_log = tmp_path / "err.log"

        filter_calls: list[int] = []

        def counting_filter(_record: dict) -> bool:
            filter_calls.append(1)
            return True

        logger.add(
            str(info_log),
            level=LogLevel.Info,
            format="{message}",
            enqueue=False,
        )
        logger.add(
            str(err_log),
            level=LogLevel.Error,
            format="{message}",
            filter=counting_filter,
            enqueue=False,
        )

        for i in range(10):
            logger.info(f"msg {i}")
        assert len(filter_calls) == 0

        logger.error("boom")
        assert len(filter_calls) >= 1

        logger.complete()

    def test_info_only_regression_filter_never_called(self, tmp_path: Path) -> None:
        """Stronger check: after many INFO lines, filter call count stays 0."""
        logger = _fresh_logger()
        info_log = tmp_path / "a.log"
        err_log = tmp_path / "b.log"

        count = 0

        def bump(_record: dict) -> bool:
            nonlocal count
            count += 1
            return True

        logger.add(str(info_log), level=LogLevel.Info, format="{message}", enqueue=False)
        logger.add(
            str(err_log),
            level=LogLevel.Error,
            format="{message}",
            filter=bump,
            enqueue=False,
        )

        for _ in range(50):
            logger.info("x")
        assert count == 0

        logger.complete()

    def test_error_callback_with_error_filtered_handler_mixed(self, tmp_path: Path) -> None:
        """ERROR-only callback + ERROR filtered file: INFO skips GIL; ERROR runs both."""
        logger = _fresh_logger()
        info_log = tmp_path / "i.log"
        err_log = tmp_path / "e.log"

        callback_hits: list[int] = []
        filter_hits: list[int] = []

        def on_record(_record: dict) -> None:
            callback_hits.append(1)

        def filt(_record: dict) -> bool:
            filter_hits.append(1)
            return True

        logger.add(str(info_log), level=LogLevel.Info, format="{message}", enqueue=False)
        logger.add(
            str(err_log),
            level=LogLevel.Error,
            format="{message}",
            filter=filt,
            enqueue=False,
        )
        logger.add_callback(on_record, level=LogLevel.Error)

        for _ in range(20):
            logger.info("info-only")
        assert len(callback_hits) == 0
        assert len(filter_hits) == 0

        logger.error("err-line")
        assert len(callback_hits) >= 1
        assert len(filter_hits) >= 1

        logger.complete()


class TestFilterFastPathCustomLevel:
    """Custom level path (_log_custom) matches built-in eligibility rules."""

    def test_custom_level_below_error_handler_skips_filter(self, tmp_path: Path) -> None:
        logger = _fresh_logger()
        info_log = tmp_path / "c.log"
        err_log = tmp_path / "d.log"

        count = 0

        def bump(_record: dict) -> bool:
            nonlocal count
            count += 1
            return True

        logger.level("NOTICE", no=35, color="cyan")
        logger.add(str(info_log), level=LogLevel.Trace, format="{message}", enqueue=False)
        logger.add(
            str(err_log),
            level=LogLevel.Error,
            format="{message}",
            filter=bump,
            enqueue=False,
        )

        logger.log("NOTICE", "n1")
        logger.log("NOTICE", "n2")
        assert count == 0

        logger.log("ERROR", "e1")
        assert count >= 1

        logger.complete()
