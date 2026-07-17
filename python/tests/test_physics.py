"""Tests for continuityguard.score.physics. Ported from src/score/physics.test.ts."""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from continuityguard.ingest.ffmpeg import FRAME_BYTES, ClipInfo, cleanup_frames, extract_frames
from continuityguard.score.physics import (
    DISCONTINUITY_MULTIPLIER,
    PhysicsShotInput,
    build_physics_reason,
    compute_diff_sequence,
    compute_frame_diff,
    detect_discontinuities,
    score_physics,
)

from .conftest import FIXTURE_DIR, requires_ffmpeg


def _frame(value: int, length: int = 12) -> bytes:
    return bytes([value]) * length


def test_compute_frame_diff_returns_0_for_identical_frames():
    assert compute_frame_diff(_frame(100), _frame(100)) == 0


def test_compute_frame_diff_returns_a_normalized_value_for_maximally_different_frames():
    assert compute_frame_diff(_frame(0), _frame(255)) == pytest.approx(1, abs=1e-5)


def test_compute_frame_diff_scales_linearly_with_the_per_channel_difference():
    diff = compute_frame_diff(_frame(0), _frame(51))
    assert diff == pytest.approx(51 / 255, abs=1e-5)


def test_compute_frame_diff_raises_when_frame_sizes_differ():
    with pytest.raises(ValueError, match="different sizes"):
        compute_frame_diff(_frame(0, 3), _frame(0, 6))


def test_compute_diff_sequence_returns_empty_for_fewer_than_2_frames():
    assert compute_diff_sequence([]) == []
    assert compute_diff_sequence([_frame(1)]) == []


def test_compute_diff_sequence_returns_length_minus_1_diffs():
    diffs = compute_diff_sequence([_frame(0), _frame(10), _frame(20)])
    assert len(diffs) == 2


class TestDetectDiscontinuities:
    def test_returns_nothing_for_an_empty_diff_sequence(self):
        assert detect_discontinuities([]) == []

    def test_flags_a_diff_exceeding_multiplier_times_the_median_baseline(self):
        found = detect_discontinuities([0.02, 0.02, 0.02, 0.5], 3)
        assert len(found) == 1
        assert found[0].frame_index_a == 3
        assert found[0].frame_index_b == 4
        assert found[0].ratio == pytest.approx(25, abs=0.1)

    def test_does_not_flag_diffs_within_the_local_baseline(self):
        found = detect_discontinuities([0.02, 0.021, 0.019, 0.022], 3)
        assert found == []

    def test_uses_the_default_discontinuity_multiplier(self):
        found = detect_discontinuities([0.01, 0.01, 0.01, 5])
        assert len(found) == 1
        assert DISCONTINUITY_MULTIPLIER > 0

    def test_handles_an_all_zero_baseline_by_flagging_any_nonzero_diff(self):
        found = detect_discontinuities([0, 0, 0.001, 0])
        assert len(found) == 1
        assert found[0].baseline == 0
        assert found[0].ratio == math.inf

    def test_does_not_flag_anything_when_baseline_and_all_diffs_are_zero(self):
        assert detect_discontinuities([0, 0, 0]) == []


class TestBuildPhysicsReason:
    def test_never_affirmatively_claims_to_detect_a_physics_violation(self):
        import re

        reason = build_physics_reason(4.2)
        assert "flags the shot for" in reason
        assert re.search(r"does not detect a physics violation", reason, re.IGNORECASE)
        stripped = re.sub(r"does not detect a physics violation", "", reason, flags=re.IGNORECASE)
        assert not re.search(r"detects? a physics violation", stripped, re.IGNORECASE)
        assert "4.2x" in reason

    def test_handles_a_non_finite_ratio_gracefully(self):
        reason = build_physics_reason(math.inf)
        assert "far above" in reason


class TestScorePhysics:
    def test_flags_nothing_for_shots_with_fewer_than_2_frames(self):
        result = score_physics([PhysicsShotInput(clip="a.mp4", frame_paths=[])])
        assert result.flagged_shots == []

    def test_reports_discontinuity_ratio_minus_1_for_a_non_finite_ratio(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zero = bytes([10]) * FRAME_BYTES
            different = bytes([200]) * FRAME_BYTES
            names = ["frame_0001.rgb", "frame_0002.rgb", "frame_0003.rgb", "frame_0004.rgb"]
            paths = [str(tmp_path / n) for n in names]
            (tmp_path / names[0]).write_bytes(zero)
            (tmp_path / names[1]).write_bytes(zero)
            (tmp_path / names[2]).write_bytes(zero)
            (tmp_path / names[3]).write_bytes(different)

            result = score_physics(
                [PhysicsShotInput(clip="zero-baseline.mp4", frame_paths=paths)]
            )
            assert len(result.flagged_shots) == 1
            assert result.flagged_shots[0].discontinuity_ratio == -1
            assert "far above" in result.flagged_shots[0].reason

    @requires_ffmpeg
    def test_flags_the_real_action_discontinuity_fixture_and_not_calm_baseline(self):
        discontinuity = extract_frames(
            ClipInfo(
                path=str(FIXTURE_DIR / "action-discontinuity.mp4"),
                name="action-discontinuity.mp4",
            )
        )
        calm = extract_frames(
            ClipInfo(path=str(FIXTURE_DIR / "calm-baseline.mp4"), name="calm-baseline.mp4")
        )
        try:
            result = score_physics(
                [
                    PhysicsShotInput(
                        clip=discontinuity.clip.name, frame_paths=discontinuity.frame_paths
                    ),
                    PhysicsShotInput(clip=calm.clip.name, frame_paths=calm.frame_paths),
                ]
            )
            flagged_clips = {f.clip for f in result.flagged_shots}
            assert "action-discontinuity.mp4" in flagged_clips
            assert "calm-baseline.mp4" not in flagged_clips
            for flag in result.flagged_shots:
                assert "flags the shot for" in flag.reason
        finally:
            cleanup_frames([discontinuity, calm])
