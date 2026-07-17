"""
CG03 -- physics-plausibility heuristic.

This is a frame-to-frame motion-discontinuity proxy, computed as the mean
absolute per-channel pixel difference between consecutive sampled frames
of a shot (a frame-diff proxy, not optical-flow motion-vector extraction
-- see the root README "Known limitations" for why this simpler proxy was
chosen for v0.1). A shot is flagged when the diff between two consecutive
frames exceeds a multiple of that shot's own local baseline (the median
frame-to-frame diff across the whole shot).

HARD RULE, enforced everywhere this feature is surfaced (CLI output, the
JSON report's `reason` field, README copy): this heuristic never "detects"
a physics violation. It only "flags a shot for human review." It has real
false positives (legitimate fast motion, intentional stylized jump-cuts)
and false negatives (subtly implausible motion that stays under the
threshold) -- it is a proxy, not a ground-truth validator.

Ported from src/score/physics.ts.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np

from ..ingest.ffmpeg import FRAME_SIZE, read_raw_frame

# A consecutive-frame diff is flagged when it exceeds this multiple of the
# shot's own median frame-to-frame diff. Derived from this repo's own
# fixture run -- see the root CHANGELOG.md "CG03 fixture calibration"
# entry for the exact command and raw numbers this value came from, not an
# illustrative placeholder. Identical to the TS side's
# DISCONTINUITY_MULTIPLIER.
DISCONTINUITY_MULTIPLIER = 3


def compute_frame_diff(a: bytes, b: bytes) -> float:
    """Mean absolute per-channel pixel difference between two same-sized
    raw RGB24 frame buffers, normalized to [0, 1]. Uses numpy for speed
    (numpy is already a transitive dependency via onnxruntime); the result
    is numerically identical to a pure-Python sum of absolute differences."""
    if len(a) != len(b):
        raise ValueError("Cannot diff frames of different sizes")
    arr_a = np.frombuffer(a, dtype=np.uint8).astype(np.int32)
    arr_b = np.frombuffer(b, dtype=np.uint8).astype(np.int32)
    total = int(np.abs(arr_a - arr_b).sum())
    return total / len(a) / 255


def compute_diff_sequence(frames: Sequence[bytes]) -> List[float]:
    """Consecutive-frame diffs for an ordered sequence of frames. Length is
    len(frames) - 1 (empty if fewer than 2 frames)."""
    return [compute_frame_diff(frames[i - 1], frames[i]) for i in range(1, len(frames))]


def _median(values: Sequence[float]) -> float:
    return statistics.median(values)


@dataclass(frozen=True)
class Discontinuity:
    frame_index_a: int
    frame_index_b: int
    diff: float
    baseline: float
    ratio: float


def detect_discontinuities(
    diffs: Sequence[float], multiplier: float = DISCONTINUITY_MULTIPLIER
) -> List[Discontinuity]:
    """Pure detection logic over an already-computed diff sequence -- split
    out from `score_physics` so it has fast, deterministic unit-test
    coverage independent of ffmpeg/frame extraction."""
    if not diffs:
        return []
    baseline = _median(diffs)
    found: List[Discontinuity] = []
    for index, diff in enumerate(diffs):
        if baseline == 0:
            # A perfectly static baseline (e.g. an all-static shot) makes
            # any ratio computation divide-by-zero/undefined; only flag if
            # there is any motion at all against a genuinely zero baseline.
            if diff > 0:
                found.append(
                    Discontinuity(
                        frame_index_a=index,
                        frame_index_b=index + 1,
                        diff=diff,
                        baseline=baseline,
                        ratio=float("inf"),
                    )
                )
            continue
        ratio = diff / baseline
        if ratio > multiplier:
            found.append(
                Discontinuity(
                    frame_index_a=index,
                    frame_index_b=index + 1,
                    diff=diff,
                    baseline=baseline,
                    ratio=ratio,
                )
            )
    return found


def build_physics_reason(ratio: float) -> str:
    ratio_text = f"{ratio:.1f}x" if ratio != float("inf") else "far above"
    return (
        f"Frame-to-frame motion discontinuity {ratio_text} this shot's local baseline. "
        "This is a heuristic proxy, not a physics simulator -- it flags the shot for "
        "human review, it does not detect a physics violation. Expect both false "
        "positives (legitimate fast motion, stylized jump-cuts) and false negatives."
    )


@dataclass(frozen=True)
class PhysicsShotInput:
    clip: str
    frame_paths: List[str]


@dataclass(frozen=True)
class PhysicsFlag:
    clip: str
    frame_index_a: int
    frame_index_b: int
    discontinuity_ratio: float
    reason: str


@dataclass(frozen=True)
class PhysicsResult:
    flagged_shots: List[PhysicsFlag] = field(default_factory=list)


def score_physics(
    shots: Sequence[PhysicsShotInput], multiplier: Optional[float] = None
) -> PhysicsResult:
    """End-to-end CG03 entry point: reads every shot's sampled raw frames
    from disk, computes the diff sequence, and flags discontinuities."""
    flagged_shots: List[PhysicsFlag] = []
    active_multiplier = DISCONTINUITY_MULTIPLIER if multiplier is None else multiplier
    for shot in shots:
        if len(shot.frame_paths) < 2:
            continue
        frames = [read_raw_frame(frame_path) for frame_path in shot.frame_paths]
        diffs = compute_diff_sequence(frames)
        discontinuities = detect_discontinuities(diffs, active_multiplier)
        for d in discontinuities:
            flagged_shots.append(
                PhysicsFlag(
                    clip=shot.clip,
                    frame_index_a=d.frame_index_a,
                    frame_index_b=d.frame_index_b,
                    discontinuity_ratio=round(d.ratio, 2) if d.ratio != float("inf") else -1,
                    reason=build_physics_reason(d.ratio),
                )
            )
    return PhysicsResult(flagged_shots=flagged_shots)


# Re-exported so callers (CLI, tests) can reference the expected frame size
# without importing from continuityguard.ingest directly.
EXPECTED_FRAME_SIZE = FRAME_SIZE
