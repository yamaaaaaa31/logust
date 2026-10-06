"""Tests for loguru-compatible file sink options.

Covers ``compression=`` formats, ``mode=``, ``encoding=``, ``delay=`` and
``catch=``.
"""

from __future__ import annotations

import bz2
import gzip
import io
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from logust import Logger, LogLevel

ARCHIVE_FORMATS = ["gz", "bz2", "zip", "tar", "tar.gz", "tar.bz2"]


def _read_archive(path: Path, fmt: str) -> str:
    """Return the text of the single log file stored in a rotated archive."""
    if fmt == "gz":
        return gzip.decompress(path.read_bytes()).decode()
    if fmt == "bz2":
        return bz2.decompress(path.read_bytes()).decode()
    if fmt == "zip":
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            (name,) = archive.namelist()
            assert path.name == f"{name}.zip"
            return archive.read(name).decode()
    with tarfile.open(path) as archive:
        (member,) = archive.getmembers()
        assert path.name == f"{member.name}.{fmt}"
        extracted = archive.extractfile(member)
        assert extracted is not None
        return extracted.read().decode()


def _archives(directory: Path, fmt: str) -> list[Path]:
    # Rotated names look like ``app.<timestamp>.pid<pid>.log.<fmt>``.
    return sorted(p for p in directory.iterdir() if p.name.endswith(f".log.{fmt}"))


class TestCompressionFormats:
    """compression= accepts loguru's format strings."""

    @pytest.mark.parametrize("fmt", ARCHIVE_FORMATS)
    def test_rotation_compression_retention_round_trip(
        self, session_logger: Logger, tmp_path: Path, fmt: str
    ) -> None:
        log_file = tmp_path / "app.log"
        handler_id = session_logger.add(
            log_file,
            level=LogLevel.Trace,
            format="{message}",
            rotation="200 B",
            retention=2,
            compression=fmt,
        )
        try:
            for i in range(40):
                session_logger.info(f"message {i:03d} " + "x" * 30)
            session_logger.complete()
        finally:
            session_logger.remove(handler_id)

        archives = _archives(tmp_path, fmt)
        assert len(archives) == 2, [p.name for p in tmp_path.iterdir()]
        # No uncompressed rotated files are left behind.
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".log") and p != log_file]

        for archive in archives:
            lines = _read_archive(archive, fmt).splitlines()
            assert lines
            assert all(line.startswith("message ") for line in lines)

        assert "message 039" in log_file.read_text()

    def test_true_keeps_gzip(self, session_logger: Logger, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        handler_id = session_logger.add(
            log_file, format="{message}", rotation="100 B", compression=True
        )
        try:
            for i in range(10):
                session_logger.info(f"gzip message {i} " + "y" * 30)
            session_logger.complete()
        finally:
            session_logger.remove(handler_id)

        archives = _archives(tmp_path, "gz")
        assert archives
        assert "gzip message 0" in _read_archive(archives[0], "gz")

    def test_false_keeps_plain_rotated_files(self, session_logger: Logger, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        handler_id = session_logger.add(
            log_file, format="{message}", rotation="100 B", compression=False
        )
        try:
            for i in range(10):
                session_logger.info(f"plain message {i} " + "z" * 30)
            session_logger.complete()
        finally:
            session_logger.remove(handler_id)

        rotated = [p for p in tmp_path.iterdir() if p.name.startswith("app.20")]
        assert rotated
        assert all(p.suffix == ".log" for p in rotated)

    def test_retention_cleans_archives_of_other_formats(
        self, session_logger: Logger, tmp_path: Path
    ) -> None:
        stale = [
            tmp_path / f"app.2000-01-0{i}_00-00-00_000000.pid0.log.{ext}"
            for i, ext in enumerate(["zip", "tar.gz", "gz"], start=1)
        ]
        for path in stale:
            path.write_bytes(b"stale")
        unrelated = tmp_path / "app.backup.zip"
        unrelated.write_bytes(b"keep")

        handler_id = session_logger.add(
            tmp_path / "app.log",
            format="{message}",
            rotation="10 B",
            retention=0,
            compression="tar.bz2",
        )
        try:
            session_logger.info("first message")
            session_logger.info("second message")
            session_logger.complete()
        finally:
            session_logger.remove(handler_id)

        assert not any(path.exists() for path in stale)
        assert unrelated.exists()

    @pytest.mark.parametrize("fmt", ["xz", "lzma", "tar.xz"])
    def test_lzma_formats_are_rejected(
        self, session_logger: Logger, tmp_path: Path, fmt: str
    ) -> None:
        with pytest.raises(ValueError, match="not supported"):
            session_logger.add(tmp_path / "app.log", compression=fmt)
        assert not (tmp_path / "app.log").exists()

    def test_unknown_format_is_rejected(self, session_logger: Logger, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid compression format"):
            session_logger.add(tmp_path / "app.log", compression="rar")

    @pytest.mark.parametrize("value", [lambda path: None, 1])
    def test_non_bool_non_str_is_rejected(
        self, session_logger: Logger, tmp_path: Path, value: object
    ) -> None:
        with pytest.raises(TypeError):
            session_logger.add(tmp_path / "app.log", compression=value)  # type: ignore[arg-type]


class TestMode:
    """mode= selects append or truncate."""

    def test_default_appends(self, session_logger: Logger, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        log_file.write_text("old line\n")
        handler_id = session_logger.add(log_file, format="{message}")
        session_logger.info("new line")
        session_logger.remove(handler_id)
        assert log_file.read_text() == "old line\nnew line\n"

    def test_w_truncates(self, session_logger: Logger, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        log_file.write_text("old line\n")
        handler_id = session_logger.add(log_file, format="{message}", mode="w")
        assert log_file.read_text() == ""
        session_logger.info("new line")
        session_logger.remove(handler_id)
        assert log_file.read_text() == "new line\n"

    def test_invalid_mode(self, session_logger: Logger, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid file mode"):
            session_logger.add(tmp_path / "app.log", mode="r")
        assert not (tmp_path / "app.log").exists()


class TestDelay:
    """delay=True creates the file on the first message.

    enqueue=True variants live in the Rust unit tests: spawning an async writer
    thread in the pytest process makes later fork-based tests flaky on macOS.
    """

    def test_file_created_on_first_message(self, session_logger: Logger, tmp_path: Path) -> None:
        log_file = tmp_path / "nested" / "app.log"
        handler_id = session_logger.add(log_file, format="{message}", delay=True)
        try:
            assert not log_file.parent.exists()
            session_logger.complete()
            assert not log_file.exists()

            session_logger.info("first message")
            session_logger.complete()
            assert log_file.read_text() == "first message\n"
        finally:
            session_logger.remove(handler_id)

    def test_remove_without_messages_creates_nothing(
        self, session_logger: Logger, tmp_path: Path
    ) -> None:
        log_file = tmp_path / "app.log"
        handler_id = session_logger.add(log_file, delay=True, rotation="1 MB")
        session_logger.remove(handler_id)
        assert list(tmp_path.iterdir()) == []

    def test_delay_with_mode_w_truncates_on_first_message(
        self, session_logger: Logger, tmp_path: Path
    ) -> None:
        log_file = tmp_path / "app.log"
        log_file.write_text("old line\n")
        handler_id = session_logger.add(log_file, format="{message}", mode="w", delay=True)
        try:
            assert log_file.read_text() == "old line\n"
            session_logger.info("new line")
            session_logger.info("another line")
        finally:
            session_logger.remove(handler_id)
        assert log_file.read_text() == "new line\nanother line\n"


class TestEncoding:
    """encoding= only accepts UTF-8 aliases."""

    @pytest.mark.parametrize("encoding", ["utf-8", "UTF-8", "utf8", "utf_8", "U8"])
    def test_utf8_aliases(self, session_logger: Logger, tmp_path: Path, encoding: str) -> None:
        log_file = tmp_path / "app.log"
        handler_id = session_logger.add(log_file, format="{message}", encoding=encoding)
        session_logger.info("héllo 世界")
        session_logger.remove(handler_id)
        assert log_file.read_bytes() == "héllo 世界\n".encode()

    @pytest.mark.parametrize("encoding", ["latin-1", "utf-16", "ascii", "not-a-codec"])
    def test_other_encodings_rejected(
        self, session_logger: Logger, tmp_path: Path, encoding: str
    ) -> None:
        with pytest.raises(ValueError, match="encoding"):
            session_logger.add(tmp_path / "app.log", encoding=encoding)
        assert not (tmp_path / "app.log").exists()


class TestFileOnlyOptions:
    """File-only options raise TypeError for other sinks, like loguru."""

    @pytest.mark.parametrize(
        "kwargs", [{"mode": "w"}, {"encoding": "utf-8"}, {"delay": True}, {"delay": False}]
    )
    @pytest.mark.parametrize("sink_kind", ["callable", "stream", "stderr"])
    def test_rejected_for_non_file_sinks(
        self, session_logger: Logger, kwargs: dict[str, object], sink_kind: str
    ) -> None:
        sinks: dict[str, object] = {
            "callable": lambda message: None,
            "stream": io.StringIO(),
            "stderr": sys.__stderr__,
        }
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            session_logger.add(sinks[sink_kind], **kwargs)  # type: ignore[arg-type]


def _failing_sink(message: str) -> None:
    raise RuntimeError("sink exploded")


class TestCatch:
    """catch= controls what happens when a sink fails."""

    def test_default_is_silent(
        self, session_logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handler_id = session_logger.add(_failing_sink)
        try:
            session_logger.info("message")
        finally:
            session_logger.remove(handler_id)
        assert capsys.readouterr().err == ""

    @pytest.mark.parametrize("serialize", [False, True])
    def test_true_reports_to_stderr(
        self, session_logger: Logger, capsys: pytest.CaptureFixture[str], serialize: bool
    ) -> None:
        handler_id = session_logger.add(_failing_sink, catch=True, serialize=serialize)
        try:
            session_logger.info("reported message")
        finally:
            session_logger.remove(handler_id)
        err = capsys.readouterr().err
        assert f"--- Logging error in Logust Handler #{handler_id} ---" in err
        assert "reported message" in err
        assert "RuntimeError: sink exploded" in err
        assert "--- End of logging error ---" in err

    def test_true_reports_filter_errors(
        self, session_logger: Logger, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def bad_filter(record: dict[str, object]) -> bool:
            raise KeyError("filter exploded")

        messages: list[str] = []
        handler_id = session_logger.add(messages.append, filter=bad_filter, catch=True)
        try:
            session_logger.info("filtered")
        finally:
            session_logger.remove(handler_id)
        assert messages == []
        assert "filter exploded" in capsys.readouterr().err

    def test_false_raises_and_other_sinks_still_run(self, session_logger: Logger) -> None:
        received: list[str] = []
        good_id = session_logger.add(received.append, format="{message}")
        bad_id = session_logger.add(_failing_sink, catch=False)
        try:
            with pytest.raises(RuntimeError, match="sink exploded"):
                session_logger.info("raised message")
            with pytest.raises(RuntimeError, match="sink exploded"):
                session_logger.log("WARNING", "custom level path")
        finally:
            session_logger.remove(bad_id)
            session_logger.remove(good_id)
        assert received == ["raised message", "custom level path"]

    def test_false_on_stream_sink(self, session_logger: Logger) -> None:
        class BrokenStream:
            def write(self, message: str) -> None:
                raise OSError("stream closed")

        handler_id = session_logger.add(BrokenStream(), catch=False)
        try:
            with pytest.raises(OSError, match="stream closed"):
                session_logger.info("message")
        finally:
            session_logger.remove(handler_id)

    def _unwritable_path(self, tmp_path: Path) -> Path:
        # The parent "directory" is a regular file, so opening fails.
        blocker = tmp_path / "blocker"
        blocker.write_text("")
        return blocker / "app.log"

    def test_file_sink_default_is_silent(
        self, session_logger: Logger, tmp_path: Path, capfd: pytest.CaptureFixture[str]
    ) -> None:
        handler_id = session_logger.add(self._unwritable_path(tmp_path), delay=True)
        try:
            session_logger.info("message")
        finally:
            session_logger.remove(handler_id)
        assert "Logging error" not in capfd.readouterr().err

    def test_file_sink_true_reports(
        self, session_logger: Logger, tmp_path: Path, capfd: pytest.CaptureFixture[str]
    ) -> None:
        handler_id = session_logger.add(self._unwritable_path(tmp_path), delay=True, catch=True)
        try:
            session_logger.info("file message")
        finally:
            session_logger.remove(handler_id)
        err = capfd.readouterr().err
        assert f"--- Logging error in Logust Handler #{handler_id} ---" in err
        assert "file message" in err

    def test_file_sink_false_raises_oserror(self, session_logger: Logger, tmp_path: Path) -> None:
        handler_id = session_logger.add(self._unwritable_path(tmp_path), delay=True, catch=False)
        try:
            with pytest.raises(OSError):
                session_logger.info("message")
        finally:
            session_logger.remove(handler_id)


class TestConfigure:
    """The new options are accepted by configure(handlers=[...])."""

    def test_configure_threads_options(self, session_logger: Logger, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        log_file.write_text("old line\n")
        lazy_file = tmp_path / "lazy.log"
        handler_ids = session_logger.configure(
            handlers=[
                {
                    "sink": str(log_file),
                    "format": "{message}",
                    "mode": "w",
                    "encoding": "utf8",
                    "compression": "zip",
                    "rotation": "1 MB",
                    "catch": True,
                },
                {"sink": str(lazy_file), "delay": True},
            ]
        )
        try:
            assert not lazy_file.exists()
            assert log_file.read_text() == ""
        finally:
            for handler_id in handler_ids:
                session_logger.remove(handler_id)

    def test_configure_rejects_file_options_for_streams(self, session_logger: Logger) -> None:
        with pytest.raises(TypeError):
            session_logger.configure(handlers=[{"sink": io.StringIO(), "mode": "w"}])


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("rotation", "12:00"),
        ("rotation", "1 week"),
        ("rotation", "monday at 12:00"),
        ("retention", "1 week"),
        ("retention", "forever"),
    ],
)
def test_unsupported_rotation_and_retention_are_rejected(
    session_logger: Logger, tmp_path: Path, option: str, value: str
) -> None:
    with pytest.raises(ValueError, match=f"Unsupported {option}"):
        session_logger.add(tmp_path / "app.log", **{option: value})
