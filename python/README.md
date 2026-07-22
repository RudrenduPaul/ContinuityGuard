# continuityguard-cli (Python)

A local, zero-network CLI and library that scores already-generated AI
short-drama video clips for character-consistency drift and
physically-implausible motion, before you spend render credits finding out
the hard way.

[![PyPI version](https://img.shields.io/pypi/v/continuityguard-cli.svg)](https://pypi.org/project/continuityguard-cli/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/RudrenduPaul/ContinuityGuard/blob/main/LICENSE)
[![Python versions](https://img.shields.io/pypi/pyversions/continuityguard-cli.svg)](https://pypi.org/project/continuityguard-cli/)

## Why this exists

AI short-drama generation ships hundreds of new titles a day, and every
title is assembled from many separately generated shots. Generation models
drift: a character's face shifts slightly between cuts, or a motion jumps
in a way that reads as physically wrong the moment a human watches it.
Catching that after render is expensive. ContinuityGuard scans a folder of
already-generated clips and flags the shots worth a second look before you
commit to a re-render. This package is the Python distribution -- a
genuine, independent port of the
[TypeScript/npm CLI](https://github.com/RudrenduPaul/ContinuityGuard), not
a wrapper around a Node process. It ships the exact same bundled
MobileNetV2 ONNX model file the TypeScript side uses, so both runtimes
score identical input against the same weights.

**Both distributions are published today.** The TypeScript/npm package is
on the npm registry (`npm install -g continuityguard-cli`) and this PyPI
package is on PyPI, both shipping the same scoring logic and the same
bundled MobileNetV2 ONNX model -- see the [project
README](https://github.com/RudrenduPaul/ContinuityGuard#readme) for the
TypeScript CLI reference.

## Install

```bash
pip install continuityguard-cli
```

or with [uv](https://docs.astral.sh/uv/):

```bash
uv add continuityguard-cli
```

You also need a system `ffmpeg` install (`brew install ffmpeg` on macOS,
`apt install ffmpeg` on Debian/Ubuntu) -- see "Requirements" below for why
ffmpeg is not bundled. Everything else -- the 14MB MobileNetV2 ONNX model,
the scoring logic, the CLI -- ships inside the wheel; nothing else is
fetched at scan time.

## Quickstart

Clone the repo to get the bundled fixture clips (not part of the published
wheel -- they're demo/test content):

```bash
git clone https://github.com/RudrenduPaul/ContinuityGuard.git
cd ContinuityGuard
continuityguard scan src/score/testdata/clips
```

Real output, from this repo's own committed synthetic fixtures (no real
short-drama footage was available for this port; every number is
reproducible against the fixtures, not illustrative):

```
$ continuityguard scan src/score/testdata/clips

ContinuityGuard v0.1 -- Local Character-Consistency & Physics-QA Scoring

Scanning: /path/to/ContinuityGuard/src/score/testdata/clips (8 clips, ffmpeg decode)

[SCORED] CG01 Clip Ingestion
  8 clips decoded, 51 frames extracted

[SCORED] CG02 Character-Consistency Scoring
  3 named characters tracked across 8 clips
  1 shot(s) flagged: low cross-shot similarity (below 0.88 cosine threshold)
    kenji_shot02.mp4 -- "kenji" similarity 0.77 vs. reference (kenji_shot01.mp4)
  NOTE: consistency scoring is best-validated on photorealistic content.
  Accuracy on stylized/anime-adjacent character designs is unverified --
  treat flags on stylized content as a prompt for human review, not a
  confirmed defect. See README "Known limitations."

[SCORED] CG03 Physics-Plausibility Heuristic
  2 shot(s) flagged: frame-to-frame motion discontinuity above threshold
    action-discontinuity.mp4 @ frame 4-5 -- discontinuity 8.25x local baseline
    action-discontinuity.mp4 @ frame 5-6 -- discontinuity 8.32x local baseline
  This is a heuristic proxy, not a physics simulator. It flags shots for
  human review. It does not "detect" a physics violation.

Report written to ./continuityguard-report.json
Human-readable summary above. Use --json for the full structured report.
Scan time: <N>s. Nothing left this machine. No network calls were made.
```

These are the same fixtures and the same threshold/multiplier constants
(`CONSISTENCY_SIMILARITY_THRESHOLD = 0.88`, `DISCONTINUITY_MULTIPLIER = 3`)
as the TypeScript source -- see the root `CHANGELOG.md` "CG02/CG03 fixture
calibration" entries for the exact raw numbers those constants came from.

Or call the library directly (the agent-native path):

```python
from continuityguard import scan

report = scan("./generated-clips")
print(f"{len(report.character_consistency.flagged_shots)} consistency flag(s)")
for flag in report.physics_plausibility.flagged_shots:
    print(f"{flag.clip} @ frame {flag.frame_index_a}-{flag.frame_index_b}: {flag.reason}")
```

## CLI reference

Real, current `--help` output from the installed CLI:

```
$ continuityguard --help
usage: continuityguard [-h] [-V] {scan} ...

Free, local-first CLI that scores already-generated AI short-drama clips/frames
for character-consistency and physics-plausibility problems. Zero network calls.

positional arguments:
  {scan}
    scan         scan a directory of generated clips for character-consistency
                 and physics-plausibility flags

options:
  -h, --help     show this help message and exit
  -V, --version  show program's version number and exit

$ continuityguard scan --help
usage: continuityguard scan [-h] [--json] [--fps FPS] [--out OUT] directory

scan a directory of generated clips for character-consistency and
physics-plausibility flags

positional arguments:
  directory   directory of video clips to scan

options:
  -h, --help  show this help message and exit
  --json      print the full machine-readable JSON report to stdout instead
              of a terminal summary
  --fps FPS   frame sample rate for ingestion (default: 2.3)
  --out OUT   path to write the JSON report file to (default:
              ./continuityguard-report.json)
```

### Naming your clips so CG02 can track characters

CG02 infers which character a clip belongs to from its filename, using a
`<character>_<shot-id>.<ext>` convention (for example `mei_shot01.mp4`,
`mei_shot02.mp4`). Clips sharing a character prefix are compared against
that character's first-seen shot. Clips that don't match the convention are
still decoded and scored by CG03, just not compared for character
consistency.

## How it works

```
directory of clips -> ffmpeg frame extraction (CG01, 2.3fps, 224x224 RGB24)
   -> MobileNetV2 ONNX embeddings, cosine similarity vs. reference shot (CG02)
   -> frame-to-frame diff vs. shot's own local median baseline (CG03)
   -> terminal report + JSON report (CG04)
```

Full module-by-module documentation is in
[docs/concepts.md](https://github.com/RudrenduPaul/ContinuityGuard/blob/main/docs/concepts.md).

## Requirements

- Python >= 3.9.
- A system `ffmpeg` install on `PATH`. Not bundled: a static per-platform
  ffmpeg build would be materially larger than this package's own
  dependency footprint and its licensing terms shift between LGPL and GPL
  depending on which codecs are compiled in -- a review this project isn't
  taking on before there's evidence of real usage. `continuityguard scan`
  checks for ffmpeg at startup and prints the exact install command for
  your OS if it's missing.

## Known limitations (read before trusting a flag)

Identical caveats to the TypeScript CLI, since both run the same scoring
logic against the same model:

- Character-consistency scoring is best-validated on photorealistic
  content. Its accuracy on stylized or anime-adjacent character designs,
  which describes most short-drama content, is genuinely unverified.
- The consistency embedding (MobileNetV2's ImageNet-logit vector) measures
  general visual similarity -- color, texture, coarse shape -- not a
  dedicated face-identity embedding. See
  `src/continuityguard/score/models/NOTICE.md` for why this model was used
  instead of a purpose-built face/CLIP embedding model.
- Physics-plausibility scoring is a frame-to-frame diff heuristic, not a
  physics simulator. Expect both false positives (legitimate fast motion,
  stylized jump-cuts) and false negatives.
- Thresholds are calibrated on a small, fully synthetic fixture set
  (solid-color clips, no real faces or recorded motion). See the root
  `CHANGELOG.md` for the exact numbers and the command that produced them.

## Fidelity to the TypeScript source

This is a line-for-line port of the scoring math (`preprocess_frame`,
`cosine_similarity`, `compute_frame_diff`, `detect_discontinuities`) and
uses the identical bundled `mobilenetv2-7.onnx` weights. On this repo's
own fixture clips, the Python CLI reproduces the same flagged shots at the
same thresholds as the TypeScript CLI's documented benchmark (see the root
README's "What it does" section for the reference numbers). Floating-point
inference results can differ in the last few decimal places between
`onnxruntime` (Python) and `onnxruntime-node` (the same underlying ONNX
Runtime project, different language binding) on some hardware; this does
not change which shots cross the fixed 0.88 / 3x thresholds on the
committed fixtures.

## CI integration

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with:
    python-version: '3.12'
- run: sudo apt-get update && sudo apt-get install -y ffmpeg
- run: pip install continuityguard-cli
- run: continuityguard scan ./generated-clips --json --out report.json
```

Full walkthrough in
[docs/integrations/ci.md](https://github.com/RudrenduPaul/ContinuityGuard/blob/main/docs/integrations/ci.md).

## Security

ContinuityGuard never `eval()`s or dynamically executes anything read from
a scanned clip; clip bytes are only ever decoded by ffmpeg (invoked with an
explicit argument list, never a shell string) and read back as raw pixel
data. See
[SECURITY.md](https://github.com/RudrenduPaul/ContinuityGuard/blob/main/SECURITY.md)
for the disclosure process. **Honest note**: this project does not
currently publish SLSA provenance, Sigstore signatures, or an SBOM, and has
no OpenSSF Scorecard badge -- none of that infrastructure exists yet, so it
isn't claimed here.

## Contributing

See [CONTRIBUTING.md](https://github.com/RudrenduPaul/ContinuityGuard/blob/main/CONTRIBUTING.md).

```bash
cd python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0, see [LICENSE](https://github.com/RudrenduPaul/ContinuityGuard/blob/main/LICENSE).
