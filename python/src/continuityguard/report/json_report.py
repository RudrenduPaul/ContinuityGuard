"""
CG04 -- machine-readable JSON report output (`--json` mode). Built so a
QA agent or CI pipeline can parse scan results programmatically, with the
same "no bare pass/fail" guarantee as the terminal report: every flagged
shot carries a reason string alongside its numeric score.

Ported from src/report/json.ts. Named json_report.py (not json.py) so it
never shadows the stdlib `json` module it imports.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Union

from .types import ScanReport


class UnsafeOutputPathError(ValueError):
    pass


# --out is a plain CLI flag today, but this CLI is also meant to be invoked
# programmatically by agents that may derive the value from less-trusted
# input. A relative path containing ".." segments can escape the intended
# output location entirely (--out ../../../etc/cron.d/x) -- reject any
# --out value that resolves outside the current working directory. An
# explicit absolute path is still allowed: that's a value the caller
# typed/passed directly, not one that silently escaped via traversal.
def _assert_safe_output_path(file_path: Union[str, Path]) -> None:
    file_path = str(file_path)
    if os.path.isabs(file_path):
        return
    cwd = os.path.realpath(os.getcwd())
    resolved = os.path.realpath(os.path.join(cwd, file_path))
    if resolved != cwd and not resolved.startswith(cwd + os.sep):
        raise UnsafeOutputPathError(
            f'--out "{file_path}" resolves outside the current working directory '
            f"({resolved}). Pass an absolute path if you intend to write outside "
            "the working directory."
        )


def serialize_report(report: ScanReport) -> str:
    return json.dumps(asdict(report), indent=2) + "\n"


def write_json_report(path: Union[str, Path], report: ScanReport) -> None:
    _assert_safe_output_path(path)
    Path(path).write_text(serialize_report(report), encoding="utf-8")
