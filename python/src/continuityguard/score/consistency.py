"""
CG02 -- character-consistency scoring.

Computes a per-shot visual embedding and flags cross-shot pairs (claiming
to be the same named character) whose cosine similarity falls below a
threshold derived from this repo's own fixture run (see
src/score/testdata/ and the root CHANGELOG.md's "CG02 fixture
calibration" entry -- never an invented number; the Python port reuses
the exact same threshold since it uses the exact same bundled model file
and the same fixture clips).

IMPORTANT, stated plainly and repeated in the CLI output, the JSON
`reason` field, and the README: this technique is best-validated on
photorealistic/live-action content. Its accuracy on stylized or
anime-adjacent character designs -- the dominant visual style in the
short-drama category this tool targets -- is UNVERIFIED. Treat a flag on
stylized footage as "worth a second look," never as a confirmed defect.

Runtime note: this port uses `onnxruntime` (the Python package), the same
ONNX Runtime project as the TS side's `onnxruntime-node`, loading the
identical bundled `mobilenetv2-7.onnx` file the npm package ships (see
models/NOTICE.md for the model's provenance and the honest limitations of
using a generic ImageNet feature extractor instead of a dedicated face/CLIP
embedding model). Same model file, same runtime family, same preprocessing
-> same embeddings and the same flagged shots as the TypeScript CLI on
identical input.

Ported from src/score/consistency.ts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import onnxruntime as ort

from ..ingest.ffmpeg import FRAME_SIZE, read_raw_frame

_MODEL_PATH = Path(__file__).resolve().parent / "models" / "mobilenetv2-7.onnx"

# ImageNet normalization constants used by the bundled MobileNetV2 model's
# documented preprocessing (see continuityguard/score/models/NOTICE.md).
_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)

# Cross-shot cosine-similarity threshold below which a shot is flagged as a
# likely character-consistency break. Derived from this repo's own fixture
# run -- see the root CHANGELOG.md "CG02 fixture calibration" entry for the
# exact command and raw numbers this value came from, not an illustrative
# placeholder. Identical to the TS side's CONSISTENCY_SIMILARITY_THRESHOLD.
CONSISTENCY_SIMILARITY_THRESHOLD = 0.88

_cached_session: Optional[ort.InferenceSession] = None


def get_embedding_session() -> ort.InferenceSession:
    """Loads (and caches) the bundled ONNX embedding session. Never fetches
    anything over the network -- the model file ships inside this package."""
    global _cached_session
    if _cached_session is None:
        _cached_session = ort.InferenceSession(
            str(_MODEL_PATH), providers=["CPUExecutionProvider"]
        )
    return _cached_session


def preprocess_frame(raw: bytes) -> np.ndarray:
    """Converts a raw HWC RGB24 frame buffer into the CHW, ImageNet-normalized
    float32 array MobileNetV2 expects, shape (3, FRAME_SIZE, FRAME_SIZE)."""
    size = FRAME_SIZE
    pixels = np.frombuffer(raw, dtype=np.uint8).reshape(size, size, 3).astype(np.float32) / 255.0
    mean = np.array(_IMAGENET_MEAN, dtype=np.float32)
    std = np.array(_IMAGENET_STD, dtype=np.float32)
    normalized = (pixels - mean) / std
    # HWC -> CHW
    return np.transpose(normalized, (2, 0, 1))


def embed_frame(raw: bytes, session: ort.InferenceSession) -> np.ndarray:
    """Runs one frame through the embedding model and returns its raw
    1000-d output vector (see models/NOTICE.md for why this is the raw
    classifier-logit vector rather than a dedicated embedding-layer
    output)."""
    input_array = preprocess_frame(raw)
    tensor = input_array.reshape(1, 3, FRAME_SIZE, FRAME_SIZE)
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    results = session.run([output_name], {input_name: tensor})
    return np.asarray(results[0], dtype=np.float32).reshape(-1)


def embed_shot(frame_paths: Sequence[str], session: ort.InferenceSession) -> np.ndarray:
    """Computes one embedding per shot by averaging the embeddings of every
    sampled frame in that shot -- smooths single-frame noise into a more
    stable per-shot signal than picking any single frame would."""
    if not frame_paths:
        raise ValueError("Cannot embed a shot with zero extracted frames")
    total: Optional[np.ndarray] = None
    for frame_path in frame_paths:
        raw = read_raw_frame(frame_path)
        embedding = embed_frame(raw, session)
        total = embedding.copy() if total is None else total + embedding
    assert total is not None
    return total / len(frame_paths)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        raise ValueError("Cannot compare embeddings of different dimensionality")
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


_CHARACTER_NAME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9]*)_")


def parse_character_name(clip_file_name: str) -> Optional[str]:
    """
    Infers the named character a clip belongs to from its filename, using
    a `<character>_<shot-id>.<ext>` convention (e.g. "mei_shot01.mp4" ->
    "mei"). This is a deliberate v0.1 simplification: there is no
    industry-standard character-tagging metadata format across AI
    short-drama pipelines, so ContinuityGuard reads it from the filename
    rather than requiring a separate manifest. Clips that don't match the
    convention return None and are never compared to each other for
    consistency (no named-character claim to check them against).
    """
    without_ext = re.sub(r"\.[^.]+$", "", clip_file_name)
    match = _CHARACTER_NAME_RE.match(without_ext)
    return match.group(1).lower() if match else None


@dataclass(frozen=True)
class ShotInput:
    clip: str
    frame_paths: List[str]


@dataclass(frozen=True)
class ConsistencyFlag:
    clip: str
    character: str
    reference_clip: str
    similarity_score: float
    reason: str


@dataclass(frozen=True)
class ConsistencyResult:
    characters_tracked: int
    flagged_shots: List[ConsistencyFlag] = field(default_factory=list)


def build_consistency_reason(similarity: float) -> str:
    """Builds the honest, unverified-content-labeled reason string for a
    flagged shot -- kept as its own function so every call site (CLI, JSON
    report) uses identical, never-drifting wording."""
    return (
        f"Cross-shot embedding similarity {similarity:.2f} is below the "
        f"{CONSISTENCY_SIMILARITY_THRESHOLD:.2f} threshold. Best-validated on "
        "photorealistic content; accuracy on stylized/anime-adjacent character designs "
        "is unverified -- treat this as a prompt for human review, not a confirmed defect."
    )


def flag_inconsistent_shots(
    shots: Sequence[Dict], threshold: float = CONSISTENCY_SIMILARITY_THRESHOLD
) -> ConsistencyResult:
    """
    Pure grouping + flagging logic, independent of the embedding model --
    given already-computed per-shot embeddings, groups by character and
    flags any shot whose similarity to that character's first-seen
    ("reference") shot falls below threshold. Split out from
    `score_consistency` so this logic has fast, deterministic unit-test
    coverage without depending on real ONNX inference for every test case.

    Each item in `shots` is a dict with keys "clip" (str) and "embedding"
    (np.ndarray).
    """
    by_character: "Dict[str, List[Dict]]" = {}
    for shot in shots:
        character = parse_character_name(shot["clip"])
        if not character:
            continue
        by_character.setdefault(character, []).append(shot)

    flagged_shots: List[ConsistencyFlag] = []
    for character, bucket in by_character.items():
        if len(bucket) < 2:
            continue
        reference = bucket[0]
        for candidate in bucket[1:]:
            similarity = cosine_similarity(reference["embedding"], candidate["embedding"])
            if similarity < threshold:
                flagged_shots.append(
                    ConsistencyFlag(
                        clip=candidate["clip"],
                        character=character,
                        reference_clip=reference["clip"],
                        similarity_score=round(similarity, 4),
                        reason=build_consistency_reason(similarity),
                    )
                )

    return ConsistencyResult(characters_tracked=len(by_character), flagged_shots=flagged_shots)


def score_consistency(
    shots: Sequence[ShotInput],
    session: Optional[ort.InferenceSession] = None,
    threshold: float = CONSISTENCY_SIMILARITY_THRESHOLD,
) -> ConsistencyResult:
    """End-to-end CG02 entry point: computes embeddings for every shot (via
    the real ONNX model) and flags cross-shot consistency breaks."""
    active_session = session or get_embedding_session()
    embedded: List[Dict] = []
    for shot in shots:
        embedding = embed_shot(shot.frame_paths, active_session)
        embedded.append({"clip": shot.clip, "embedding": embedding})
    return flag_inconsistent_shots(embedded, threshold)
