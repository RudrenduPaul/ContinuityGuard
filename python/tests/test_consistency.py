"""Tests for continuityguard.score.consistency. Ported from src/score/consistency.test.ts."""
from __future__ import annotations

import numpy as np
import pytest

from continuityguard.ingest.ffmpeg import FRAME_SIZE, cleanup_frames, extract_frames
from continuityguard.ingest.ffmpeg import ClipInfo
from continuityguard.score.consistency import (
    CONSISTENCY_SIMILARITY_THRESHOLD,
    build_consistency_reason,
    cosine_similarity,
    embed_frame,
    embed_shot,
    flag_inconsistent_shots,
    parse_character_name,
    preprocess_frame,
    score_consistency,
)

from .conftest import FIXTURE_DIR, requires_ffmpeg


class _FakeOutput:
    def __init__(self, data):
        self.data = data


class FakeSession:
    """Minimal stand-in for onnxruntime.InferenceSession, mirroring the TS
    test suite's `fakeSession` helper."""

    def __init__(self, inputs=("input",), outputs=("output",), run_result=None):
        self._inputs = inputs
        self._outputs = outputs
        self._run_result = run_result

    def get_inputs(self):
        return [type("I", (), {"name": n})() for n in self._inputs]

    def get_outputs(self):
        return [type("O", (), {"name": n})() for n in self._outputs]

    def run(self, output_names, feeds):
        if self._run_result is not None:
            return self._run_result
        return [np.array([1.0, 2.0, 3.0], dtype=np.float32)]


def test_cosine_similarity_returns_1_for_identical_vectors():
    v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert cosine_similarity(v, v) == pytest.approx(1, abs=1e-5)


def test_cosine_similarity_returns_0_for_orthogonal_vectors():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(0, abs=1e-5)


def test_cosine_similarity_returns_minus_1_for_opposite_vectors():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([-1.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(-1, abs=1e-5)


def test_cosine_similarity_returns_0_when_either_vector_is_all_zero():
    a = np.array([0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 2.0], dtype=np.float32)
    assert cosine_similarity(a, b) == 0


def test_cosine_similarity_raises_on_dimension_mismatch():
    with pytest.raises(ValueError, match="dimensionality"):
        cosine_similarity(np.array([1.0]), np.array([1.0, 2.0]))


def test_parse_character_name_extracts_the_prefix():
    assert parse_character_name("mei_shot01.mp4") == "mei"
    assert parse_character_name("Kenji_shot02.mov") == "kenji"


def test_parse_character_name_returns_none_for_non_matching_filenames():
    assert parse_character_name("action-discontinuity.mp4") is None
    assert parse_character_name("random.mp4") is None


def test_preprocess_frame_produces_a_chw_float32_array_of_the_expected_length():
    raw = bytes([128]) * (FRAME_SIZE * FRAME_SIZE * 3)
    out = preprocess_frame(raw)
    assert out.size == 3 * FRAME_SIZE * FRAME_SIZE


class TestEmbedFrameErrorHandling:
    raw = bytes([64]) * (FRAME_SIZE * FRAME_SIZE * 3)

    def test_returns_the_raw_output_vector_on_a_well_formed_session(self):
        session = FakeSession()
        embedding = embed_frame(self.raw, session)
        assert list(embedding) == [1.0, 2.0, 3.0]


def test_embed_shot_raises_on_zero_frame_paths():
    with pytest.raises(ValueError, match="zero extracted frames"):
        embed_shot([], FakeSession())


def test_build_consistency_reason_always_discloses_the_photorealistic_only_limitation():
    reason = build_consistency_reason(0.5)
    assert "photorealistic" in reason.lower()
    assert "unverified" in reason.lower()
    assert f"{CONSISTENCY_SIMILARITY_THRESHOLD:.2f}" in reason


class TestFlagInconsistentShots:
    @staticmethod
    def _embed(*values):
        return np.array(values, dtype=np.float32)

    def test_flags_a_shot_below_threshold_against_its_character_reference(self):
        result = flag_inconsistent_shots(
            [
                {"clip": "mei_shot01.mp4", "embedding": self._embed(1, 0, 0)},
                {"clip": "mei_shot02.mp4", "embedding": self._embed(0, 1, 0)},
            ],
            0.5,
        )
        assert result.characters_tracked == 1
        assert len(result.flagged_shots) == 1
        assert result.flagged_shots[0].clip == "mei_shot02.mp4"
        assert result.flagged_shots[0].reference_clip == "mei_shot01.mp4"

    def test_does_not_flag_a_shot_at_or_above_threshold(self):
        result = flag_inconsistent_shots(
            [
                {"clip": "mei_shot01.mp4", "embedding": self._embed(1, 0, 0)},
                {"clip": "mei_shot02.mp4", "embedding": self._embed(1, 0, 0)},
            ],
            0.99,
        )
        assert result.flagged_shots == []

    def test_skips_clips_whose_filename_does_not_match_the_character_convention(self):
        result = flag_inconsistent_shots(
            [
                {"clip": "random.mp4", "embedding": self._embed(1, 0, 0)},
                {"clip": "other.mp4", "embedding": self._embed(0, 1, 0)},
            ]
        )
        assert result.characters_tracked == 0
        assert result.flagged_shots == []

    def test_does_not_compare_a_character_with_only_one_shot(self):
        result = flag_inconsistent_shots(
            [{"clip": "mei_shot01.mp4", "embedding": self._embed(1, 0, 0)}]
        )
        assert result.characters_tracked == 1
        assert result.flagged_shots == []

    def test_compares_every_later_shot_to_the_first_seen_reference_shot(self):
        result = flag_inconsistent_shots(
            [
                {"clip": "mei_shot01.mp4", "embedding": self._embed(1, 0, 0)},
                {"clip": "mei_shot02.mp4", "embedding": self._embed(1, 0, 0)},
                {"clip": "mei_shot03.mp4", "embedding": self._embed(0, 1, 0)},
            ],
            0.5,
        )
        assert len(result.flagged_shots) == 1
        assert result.flagged_shots[0].clip == "mei_shot03.mp4"


@requires_ffmpeg
class TestScoreConsistencyRealOnnxInference:
    def test_does_not_flag_the_real_consistent_pair(self):
        shot1 = extract_frames(
            ClipInfo(path=str(FIXTURE_DIR / "mei_shot01.mp4"), name="mei_shot01.mp4")
        )
        shot2 = extract_frames(
            ClipInfo(path=str(FIXTURE_DIR / "mei_shot02.mp4"), name="mei_shot02.mp4")
        )
        try:
            from continuityguard.score.consistency import ShotInput

            result = score_consistency(
                [
                    ShotInput(clip=shot1.clip.name, frame_paths=shot1.frame_paths),
                    ShotInput(clip=shot2.clip.name, frame_paths=shot2.frame_paths),
                ]
            )
            assert result.flagged_shots == []
        finally:
            cleanup_frames([shot1, shot2])

    def test_flags_the_real_deliberately_inconsistent_pair(self):
        shot1 = extract_frames(
            ClipInfo(path=str(FIXTURE_DIR / "kenji_shot01.mp4"), name="kenji_shot01.mp4")
        )
        shot2 = extract_frames(
            ClipInfo(path=str(FIXTURE_DIR / "kenji_shot02.mp4"), name="kenji_shot02.mp4")
        )
        try:
            from continuityguard.score.consistency import ShotInput

            result = score_consistency(
                [
                    ShotInput(clip=shot1.clip.name, frame_paths=shot1.frame_paths),
                    ShotInput(clip=shot2.clip.name, frame_paths=shot2.frame_paths),
                ]
            )
            assert len(result.flagged_shots) == 1
            assert result.flagged_shots[0].clip == "kenji_shot02.mp4"
            assert result.flagged_shots[0].similarity_score < CONSISTENCY_SIMILARITY_THRESHOLD
        finally:
            cleanup_frames([shot1, shot2])
