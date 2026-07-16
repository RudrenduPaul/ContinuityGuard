# Contributing to ContinuityGuard

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

## Local setup

Requirements: Node.js >= 22, a system `ffmpeg` install.

```bash
git clone https://github.com/RudrenduPaul/ContinuityGuard.git
cd ContinuityGuard
npm install
npm run build
node dist/cli.js scan src/score/testdata/clips --json
```

## Before opening a PR

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

### Fixture reproducibility

Every scoring-logic change should re-run the fixtures in
`src/score/testdata/` (regenerate with `src/score/testdata/generate-fixtures.sh`
if you change what they need to demonstrate) and confirm the numbers in
this repo's own README/CHANGELOG still match a fresh run. Don't publish a
scoring number anywhere in this repo without a command that reproduces it.

### The zero-network guarantee

The single most load-bearing claim in this repo's positioning is that
`continuityguard scan` never makes an outbound network call. `npm run
verify:zero-network` proves this empirically (it monkey-patches every
network entry point Node exposes and runs a real scan against the
committed fixtures -- if anything tries to reach the network, the script
fails loudly). If your change adds a new dependency or a new code path
inside `scan`, re-run this and make sure it still passes.

## What never goes in this repo

This is a real, enforced policy, not a suggestion -- `.github/workflows/
no-internal-docs.yml` fails CI if any of the following is reintroduced:

- A root `[redacted]`, `TODOS.md`, or `BRANCH_PROTECTION.md`.
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
