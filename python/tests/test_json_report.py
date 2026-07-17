"""Tests for continuityguard.report.json_report. Ported from src/report/json.test.ts."""
from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from continuityguard.report.json_report import serialize_report, write_json_report
from continuityguard.report.types import (
    CharacterConsistencyReport,
    PhysicsPlausibilityReport,
    ScanReport,
)


def _build_sample_report() -> ScanReport:
    return ScanReport(
        scan_id="cg-test",
        scanned_directory="/tmp/clips",
        clips_scanned=2,
        frames_extracted=10,
        character_consistency=CharacterConsistencyReport(
            characters_tracked=1, similarity_threshold=0.88, flagged_shots=[]
        ),
        physics_plausibility=PhysicsPlausibilityReport(
            discontinuity_multiplier=3, flagged_shots=[]
        ),
        generated_at="2026-07-16T00:00:00.000Z",
        tool_version="0.1.0",
        scan_duration_seconds=1.23,
        network_calls_made=0,
    )


def test_serialize_report_produces_valid_pretty_printed_newline_terminated_json():
    report = _build_sample_report()
    serialized = serialize_report(report)
    assert serialized.endswith("\n")
    assert json.loads(serialized) == asdict(report)


def test_write_json_report_writes_the_serialized_report_to_disk():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.json"
        report = _build_sample_report()
        write_json_report(path, report)
        contents = path.read_text(encoding="utf-8")
        assert json.loads(contents) == asdict(report)
