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
from dataclasses import asdict
from pathlib import Path
from typing import Union

from .types import ScanReport


def serialize_report(report: ScanReport) -> str:
    return json.dumps(asdict(report), indent=2) + "\n"


def write_json_report(path: Union[str, Path], report: ScanReport) -> None:
    Path(path).write_text(serialize_report(report), encoding="utf-8")
