# Contributing to ContinuityGuard

ContinuityGuard ships two distributions of the same scoring logic: an npm
package (`continuityguard-cli`, TypeScript, repo root) and a PyPI package
(`continuityguard-cli`, Python, `python/`), both using the identical
bundled `mobilenetv2-7.onnx` model. As of this writing the PyPI package is
published and the npm package is not yet (see the root README's "Install"
section) -- please read this whole file before opening a PR, since which
section applies depends on which codebase you're touching.

Thanks for looking at this. It's a small, narrowly-scoped tool, and
contributions are welcome, especially:

- Reports of false positives/false negatives on real (not synthetic) AI
  short-drama footage, from any generation pipeline.
- Testing character-consistency scoring against stylized/anime-adjacent
  content and reporting what you find -- this is explicitly unverified in
  v0.1 (see README "Known limitations") and real data is the only thing
  that changes that.
- ffmpeg edge cases (unusual codecs/containers) the ingestion step doesn't
  handle gracefully yet.

## Working on the TypeScript package (repo root)

Requirements: Node.js >= 22, a system `ffmpeg` install.

```bash
git clone https://github.com/RudrenduPaul/ContinuityGuard.git
cd ContinuityGuard
npm install
npm run build
node dist/cli.js scan src/score/testdata/clips --json
```

### Before opening a PR (TypeScript)

Every one of these must pass -- CI enforces the same list:

```bash
npm run lint            # eslint . --max-warnings 0
npm run typecheck       # tsc --noEmit
npm run test:coverage   # vitest run --coverage
npm audit --audit-level=high
npm run verify:zero-network
```

Coverage thresholds: 80% minimum overall, 95%+ on every file under
`src/score/*.ts`. A silently wrong consistency or physics flag is worse for
this tool's whole trust premise than no flag at all, so the scoring modules
are held to a higher bar than the rest of the codebase.

### The zero-network guarantee

The single most load-bearing claim in this repo's positioning is that
`continuityguard scan` never makes an outbound network call. `npm run
verify:zero-network` proves this empirically (it monkey-patches every
network entry point Node exposes and runs a real scan against the
committed fixtures -- if anything tries to reach the network, the script
fails loudly). If your change adds a new dependency or a new code path
inside `scan`, re-run this and make sure it still passes. There is no
Python equivalent script yet; the Python package's zero-network claim is
verified by code review (no network-capable import anywhere in
`python/src/continuityguard/`) rather than a runtime monkey-patch check --
tracked as a gap to close, not silently assumed equivalent.

## Working on the Python package (`python/`)

Requirements: Python >= 3.9, a system `ffmpeg` install.

```bash
cd python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
continuityguard scan ../src/score/testdata/clips --json
```

- Source lives under `python/src/continuityguard/`, laid out to mirror the
  TypeScript module structure (`ingest/`, `score/`, `report/`, `cli.py`,
  `scan.py`) so a change in one codebase has an obvious counterpart to
  check in the other.
- The bundled ONNX model (`python/src/continuityguard/score/models/mobilenetv2-7.onnx`)
  is the exact same file as `src/score/models/mobilenetv2-7.onnx` -- if you
  ever need to update the model, update both copies together and re-verify
  fixture parity between the two CLIs.
- Tests use `pytest` (`python/tests/test_*.py`), including real end-to-end
  tests that run actual ffmpeg decode + ONNX inference against the shared
  `src/score/testdata/clips/` fixtures at the repo root -- no fixture
  duplication into `python/`.
- Build and verify a real install before opening a PR that touches
  packaging:
  ```bash
  python3 -m build python --outdir python/dist
  python3 -m venv /tmp/cg-verify && /tmp/cg-verify/bin/pip install python/dist/*.whl
  /tmp/cg-verify/bin/continuityguard scan src/score/testdata/clips
  ```

### Fixture reproducibility

Every scoring-logic change (in either codebase) should re-run the fixtures
in `src/score/testdata/` (regenerate with
`src/score/testdata/generate-fixtures.sh` if you change what they need to
demonstrate) and confirm the numbers in this repo's own README/CHANGELOG
still match a fresh run, against both CLIs. Don't publish a scoring number
anywhere in this repo without a command that reproduces it.

## What never goes in this repo

This is a real, enforced policy, not a suggestion -- `.github/workflows/
no-internal-docs.yml` fails CI if any of the following is reintroduced:

- A root `CLAUDE.md`, `TODOS.md`, or `BRANCH_PROTECTION.md`.
- Any `docs/security-review-*.md`, `docs/branch-protection.md`, or
  pre-launch/launch-draft docs.
- Source comments or docs referencing an internal review/approval process
  by name.

If you're an AI coding assistant working on this repo and need
engineering-standards context beyond what's in this file and the README,
that context lives outside this public repo -- don't recreate it here.

## Code of conduct

Be direct, be kind, assume good faith. Disagreements about scoring
thresholds or false-positive rates are welcome and should be backed by
real data (a fixture, a real clip, a reproduction) wherever possible.
