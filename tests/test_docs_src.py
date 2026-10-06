"""Run every example under docs_src/ so the documentation can't drift from the code."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

DOCS_SRC = Path(__file__).resolve().parent.parent / "docs_src"
EXAMPLES = sorted(DOCS_SRC.rglob("*.py"))
OPTIONAL_DEPS = ("fastapi", "starlette", "rich", "tqdm", "httpx")


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: str(p.relative_to(DOCS_SRC)))
def test_docs_example_runs(path: Path, tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        for dep in OPTIONAL_DEPS:
            if f"No module named '{dep}'" in result.stderr:
                pytest.skip(f"optional dependency {dep!r} is not installed")
    assert result.returncode == 0, result.stderr
