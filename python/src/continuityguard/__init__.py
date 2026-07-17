"""
ContinuityGuard: a local, zero-network library and CLI that scores
already-generated AI short-drama video clips for character-consistency
drift and physics-plausibility issues.

This is the Python port of the npm package `continuityguard-cli`
(https://github.com/RudrenduPaul/ContinuityGuard). It is a genuine,
independent port -- not a wrapper around the Node binary -- ported module
for module from the TypeScript source (src/ingest/ffmpeg.ts,
src/score/consistency.ts, src/score/physics.ts, src/report/*.ts,
src/cli.ts) and using the exact same bundled ONNX model file
(mobilenetv2-7.onnx) so both runtimes score the same input the same way.

Public API:

    from continuityguard import scan, ScanReport

    report = scan("./generated-clips")
    print(report.character_consistency.flagged_shots)
"""
from __future__ import annotations

from .report.types import (
    ConsistencyFlagReport,
    PhysicsFlagReport,
    CharacterConsistencyReport,
    PhysicsPlausibilityReport,
    ScanReport,
)
from .scan import scan, scan_async

__version__ = "0.1.0"

__all__ = [
    "scan",
    "scan_async",
    "ScanReport",
    "ConsistencyFlagReport",
    "PhysicsFlagReport",
    "CharacterConsistencyReport",
    "PhysicsPlausibilityReport",
    "__version__",
]
