"""Benchmark fixtures."""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def bench_tmp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for benchmark log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
