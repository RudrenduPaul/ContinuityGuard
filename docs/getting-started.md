# Getting started

ContinuityGuard scans a directory of already-generated AI short-drama video
clips and flags two kinds of problems before you spend render credits on a
re-shoot: character-consistency drift (a named character's face/appearance
shifting between shots) and physics-implausible motion (a frame-to-frame
jump that reads as wrong the moment a human watches it). It ships as two
independent, equally first-class packages that use the exact same bundled
MobileNetV2 ONNX model: an npm package (`continuityguard-cli`,
JavaScript/TypeScript, install-from-source only today -- see the note
below) and a PyPI package (`continuityguard-cli`, Python).

**Honest note on install paths, read this before picking one:** the
Python package is published to PyPI today (`pip install
continuityguard-cli`). The TypeScript/npm package is not yet published to
the npm registry as of this writing -- the repo's own root README says so,
and the npm registry itself returns no `continuityguard-cli` entry. If you
want the TypeScript CLI, clone the repo and build from source (see the
root README's "Install" section). This doc covers both, and is updated the
day that changes.

## Install

**pip (Python library + CLI), published today:**

```bash
pip install continuityguard-cli
```

**npm (JS/TS CLI), from source only today:**

```bash
git clone https://github.com/RudrenduPaul/ContinuityGuard.git
cd ContinuityGuard
npm install
npm run build
```

Neither path fetches anything at scan time beyond the local `ffmpeg`
binary you already have installed: the ONNX model and all scoring logic
ship inside the package itself (npm tarball/`dist/` build or Python wheel).

## Requirements

- A system `ffmpeg` install on `PATH` (`brew install ffmpeg` on macOS,
  `apt install ffmpeg` on Debian/Ubuntu). Not bundled -- see the root
  README's "Known limitations" for why. Both CLIs check for it at startup
  and print the exact install command for your OS if it's missing.
- Node.js >= 22 for the TypeScript/npm package, or Python >= 3.9 for the
  PyPI package.

## Your first scan

Both packages ship the repo's `src/score/testdata/clips/` fixtures for a
safe first run (synthetic, solid-color clips -- no real footage was
available for this build; see the root `CHANGELOG.md` for exactly how they
were generated). Clone the repo to get them (they aren't bundled inside
the published Python wheel -- they're demo/test content, not shipped
runtime content):

```bash
git clone https://github.com/RudrenduPaul/ContinuityGuard.git
cd ContinuityGuard
```

```bash
# Python CLI (after `pip install continuityguard-cli`)
continuityguard scan src/score/testdata/clips

# TypeScript CLI (after npm install && npm run build)
node dist/cli.js scan src/score/testdata/clips
```

Real output (Python CLI shown; the TypeScript CLI's output is
line-for-line identical, since both use the same bundled model, same
fixtures, and the same threshold/multiplier constants):

```
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
  confirmed defect. See root README "Known limitations."

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

Every flagged shot carries a clip name, a numeric score, and a
plain-language reason -- never a bare pass/fail.

## Using the library instead of the CLI

The Python package exports a programmatic `scan()` function for agent
frameworks or CI scripts that want to call ContinuityGuard in-process
instead of shelling out to a CLI binary:

```python
from continuityguard import scan

report = scan("./generated-clips")
print(f"{len(report.character_consistency.flagged_shots)} consistency flag(s)")
print(f"{len(report.physics_plausibility.flagged_shots)} physics flag(s)")
```

An `async` variant (`scan_async`, runs the scan in a worker thread) is also
exported for callers already inside an `asyncio` event loop -- see
`python/examples/03-agent-native-json/`.

The TypeScript source does not currently expose a separate library entry
point beyond the CLI itself (`src/cli.ts` calls the scoring modules
directly); shelling out to the built CLI with `--json` is the equivalent
integration path on that side today.

## Next steps

- [concepts.md](./concepts.md) -- what CG01-CG04 each actually do, and how
  the threshold/multiplier constants were derived.
- [integrations/ci.md](./integrations/ci.md) -- wiring ContinuityGuard into
  a CI pipeline.
- The [project README](../README.md) for the full tool comparison and
  benchmark numbers.
