# Concepts

ContinuityGuard's scan pipeline has four stages, named CG01-CG04
throughout the code and the CLI output. This document explains what each
one actually does and where its numeric thresholds came from -- every
number here traces to a real, reproducible command, not an illustrative
placeholder (see the root `CHANGELOG.md` for the exact commands and raw
output).

## The pipeline

```
directory of clips
  -> CG01 ffmpeg frame extraction (2.3fps, scaled to 224x224 RGB24)
  -> CG02 character-consistency scoring (MobileNetV2 embeddings, cosine similarity)
  -> CG03 physics-plausibility heuristic (frame-to-frame diff vs. local median baseline)
  -> CG04 report output (terminal summary + JSON report)
```

## CG01 -- clip/frame ingestion

Decodes each clip in the target directory with a system `ffmpeg` install
(never bundled -- see the root README's "Known limitations" for why),
sampling frames at 2.3fps and scaling each one to a fixed 224x224 RGB24
buffer. The fixed size matches MobileNetV2's expected input dimensions
exactly, so one decode pass serves both CG02 and CG03 -- neither needs a
separate resize step. Supported extensions: `.mp4`, `.mov`, `.mkv`,
`.webm`, `.avi`.

## CG02 -- character-consistency scoring

Computes a per-shot embedding (the mean of every sampled frame's
MobileNetV2 output vector in that shot) and flags any shot whose cosine
similarity to its character's first-seen ("reference") shot falls below
**0.88**.

**Character grouping is filename-based**, using a
`<character>_<shot-id>.<ext>` convention (e.g. `mei_shot01.mp4`,
`mei_shot02.mp4` are grouped as the same character `mei`). There is no
industry-standard character-tagging metadata format across AI short-drama
pipelines, so this is a deliberate v0.1 simplification, not an oversight.
Clips that don't match the convention are still decoded and scored by
CG03; they're simply never compared for consistency (there's no
named-character claim to check them against).

**Where 0.88 came from:** the repo's own committed synthetic fixtures
(`src/score/testdata/clips/`, no real short-drama footage was available
for this build) produced these real cosine-similarity results:

| Pair | Similarity | Same character claimed? |
|---|---|---|
| `mei_shot01.mp4` vs `mei_shot02.mp4` | 0.9975 | yes, consistent |
| `aiko_shot01.mp4` vs `aiko_shot02.mp4` | 0.9906 | yes, consistent |
| `kenji_shot01.mp4` vs `kenji_shot02.mp4` | 0.7709 | yes, deliberately inconsistent |

0.88 is the midpoint between the lowest observed consistent-pair
similarity (0.9906) and the observed inconsistent-pair similarity (0.7709)
from that actual run. This is a two-pair, fully synthetic calibration, not
a statistically robust threshold from a large labeled dataset -- expect it
to move as real-world usage reports come in.

**The model, and what it actually measures:** ContinuityGuard uses
MobileNetV2 (ImageNet-pretrained, Apache-2.0 licensed), not a dedicated
face-recognition or CLIP embedding model. See
`src/score/models/NOTICE.md` (TypeScript) /
`python/src/continuityguard/score/models/NOTICE.md` (Python) for the full
reasoning. In practice: the consistency score is a general
color/texture/coarse-shape similarity signal, real but weaker than a
dedicated face-identity embedding on photorealistic faces, and unverified
on stylized/anime-adjacent designs -- the dominant visual style in the
short-drama category this tool targets. Treat a flag on stylized footage
as "worth a second look," never a confirmed defect.

## CG03 -- physics-plausibility heuristic

A frame-to-frame motion-discontinuity proxy: the mean absolute
per-channel pixel difference between consecutive sampled frames,
normalized to `[0, 1]`. A shot is flagged when a single frame-to-frame
diff exceeds **3x** the shot's own local baseline (the median diff across
that shot).

This is a frame-diff proxy, not optical-flow motion-vector extraction --
a simpler, cheaper signal chosen for v0.1 over a heavier motion-estimation
pipeline. **It never "detects" a physics violation.** It only flags a
shot for human review, and it has real false positives (legitimate fast
motion, intentional stylized jump-cuts) and false negatives (subtly
implausible motion that stays under the threshold).

**Where 3x came from:** real frame-to-frame diffs from the same fixture
run, over `action-discontinuity.mp4` (one deliberate abrupt jump) and
`calm-baseline.mp4` (smooth motion throughout):

| Clip | Median baseline | Max observed ratio | Flagged? |
|---|---|---|---|
| `calm-baseline.mp4` | 0.0223 | ~1.14x | no |
| `action-discontinuity.mp4` | 0.060 | 8.25x-8.32x | yes, both discontinuous transitions |

3x sits comfortably above the calm baseline's real observed max (no false
positive on that fixture) and well below the deliberate discontinuity's
real observed ratios.

**Zero-baseline edge case:** if a shot's median frame-to-frame diff is
exactly 0 (a perfectly static shot), any nonzero diff is flagged directly
(reported as ratio `-1` / "far above" in the reason text) rather than
computing an undefined division-by-zero ratio.

## CG04 -- report output

Every scan produces two outputs from the same data: a human-readable
terminal summary (default) and a machine-readable JSON report (`--json`,
or always written to `--out` alongside the terminal summary). Both list
every flagged shot with its clip name, numeric score, and a plain-language
`reason` string -- the CLI never emits a bare pass/fail. The JSON report
also carries `network_calls_made: 0` on every successful scan, matching
the zero-network guarantee both CLIs enforce.

## Why two independent implementations of the same logic

The Python port (`python/src/continuityguard/`) is a genuine, from-source
port of the TypeScript scoring math -- not a wrapper that shells out to
the Node CLI. Both use the identical bundled `mobilenetv2-7.onnx` weights
and the identical threshold constants (0.88, 3x), so on the same input
they produce the same flagged shots. See `python/README.md`'s "Fidelity to
the TypeScript source" section for what can differ (last-few-decimal-place
floating point results between `onnxruntime-node` and `onnxruntime`'s
Python binding) and what cannot (which shots cross the fixed thresholds
on the committed fixtures).
