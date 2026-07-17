"""
Shared pytest fixtures/constants. FIXTURE_DIR points at the repo-root
`src/score/testdata/clips/` fixtures (shared with the TypeScript test
suite, not duplicated into python/), matching the convention this
account's other Python ports use for referencing repo-root fixtures from
`python/tests/`.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "score" / "testdata" / "clips"

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="real end-to-end tests require a system ffmpeg install",
)
