"""Tests for continuityguard.report.terminal. Ported from src/report/terminal.test.ts."""
from __future__ import annotations

from continuityguard.report.terminal import render_terminal_report
from continuityguard.report.types import (
    CharacterConsistencyReport,
    ConsistencyFlagReport,
    PhysicsFlagReport,
    PhysicsPlausibilityReport,
    ScanReport,
)


def _build_report(**overrides) -> ScanReport:
    defaults = dict(
        scan_id="cg-test",
        scanned_directory="./generated-clips",
        clips_scanned=8,
        frames_extracted=51,
        character_consistency=CharacterConsistencyReport(
            characters_tracked=3, similarity_threshold=0.88, flagged_shots=[]
        ),
        physics_plausibility=PhysicsPlausibilityReport(
            discontinuity_multiplier=3, flagged_shots=[]
        ),
        generated_at="2026-07-16T00:00:00.000Z",
        tool_version="0.1.0",
        scan_duration_seconds=0.5,
        network_calls_made=0,
    )
    defaults.update(overrides)
    return ScanReport(**defaults)


def test_renders_a_clean_summary_with_zero_flags():
    output = render_terminal_report(_build_report())
    assert "ContinuityGuard v0.1" in output
    assert "0 shots flagged (below 0.88 cosine threshold)" in output
    assert "0 shots flagged: no frame-to-frame motion discontinuity" in output
    assert "detect a physics violation" not in output


def test_renders_flagged_consistency_and_physics_shots_with_reasons():
    output = render_terminal_report(
        _build_report(
            character_consistency=CharacterConsistencyReport(
                characters_tracked=1,
                similarity_threshold=0.88,
                flagged_shots=[
                    ConsistencyFlagReport(
                        clip="kenji_shot02.mp4",
                        character="kenji",
                        reference_clip="kenji_shot01.mp4",
                        similarity_score=0.7709,
                        reason="Cross-shot embedding similarity 0.77 is below the 0.88 threshold.",
                    )
                ],
            ),
            physics_plausibility=PhysicsPlausibilityReport(
                discontinuity_multiplier=3,
                flagged_shots=[
                    PhysicsFlagReport(
                        clip="action-discontinuity.mp4",
                        frame_index_a=4,
                        frame_index_b=5,
                        discontinuity_ratio=8.25,
                        reason="Frame-to-frame motion discontinuity 8.2x this shot's local baseline.",
                    )
                ],
            ),
        )
    )
    assert "kenji_shot02.mp4" in output
    assert "similarity 0.77" in output
    assert "action-discontinuity.mp4" in output
    assert "8.25x local baseline" in output


def test_includes_the_json_report_path_line_when_provided():
    output = render_terminal_report(_build_report(), "./continuityguard-report.json")
    assert "Report written to ./continuityguard-report.json" in output


def test_omits_the_json_report_path_line_when_not_provided():
    output = render_terminal_report(_build_report())
    assert "Report written to" not in output
