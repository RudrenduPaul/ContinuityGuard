"""
CG04 -- shared report shape consumed by both the JSON writer
(continuityguard/report/json_report.py) and the terminal writer
(continuityguard/report/terminal.py). Every flagged shot carries a
timestamp/frame index, a numeric score, and a plain-language reason --
never a bare pass/fail -- so a human reviewer or a parsing agent knows
*why* a shot was flagged.

Ported field-for-field from src/report/types.ts. Field names use
snake_case (not the TS camelCase) since that's the Python-idiomatic
convention and this matches the JSON keys the TS side already serializes
(the TS `ScanReport` interface itself uses snake_case JSON field names,
e.g. `scanned_directory`, `character_consistency`) -- so the JSON report
produced by this Python port is structurally identical to the TS one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class ConsistencyFlagReport:
    clip: str
    character: str
    reference_clip: str
    similarity_score: float
    reason: str


@dataclass(frozen=True)
class PhysicsFlagReport:
    clip: str
    frame_index_a: int
    frame_index_b: int
    discontinuity_ratio: float
    reason: str


@dataclass(frozen=True)
class CharacterConsistencyReport:
    characters_tracked: int
    similarity_threshold: float
    flagged_shots: List[ConsistencyFlagReport] = field(default_factory=list)


@dataclass(frozen=True)
class PhysicsPlausibilityReport:
    discontinuity_multiplier: float
    flagged_shots: List[PhysicsFlagReport] = field(default_factory=list)


@dataclass(frozen=True)
class ScanReport:
    scan_id: str
    scanned_directory: str
    clips_scanned: int
    frames_extracted: int
    character_consistency: CharacterConsistencyReport
    physics_plausibility: PhysicsPlausibilityReport
    generated_at: str
    tool_version: str
    scan_duration_seconds: float
    network_calls_made: int = 0
