# CI integrations

ContinuityGuard is meant to run as a QA gate right after a render batch
finishes: scan the output directory, and fail the job if anything is
flagged for human review. `--json` gives you a machine-readable report an
agent or CI script can parse; the CLI itself always exits `0` on a clean
scan and `1` when the scan completed but any shot was flagged (or when the
scan itself failed to run, e.g. a missing directory or missing ffmpeg --
see `docs/getting-started.md` for the full exit-code list).

## GitHub Actions -- Python CLI

```yaml
name: ContinuityGuard
on: [pull_request]

jobs:
  continuityguard-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: sudo apt-get update && sudo apt-get install -y ffmpeg
      - run: pip install continuityguard-cli
      - name: Scan generated clips
        run: continuityguard scan ./generated-clips --json --out continuityguard-report.json
      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: continuityguard-report
          path: continuityguard-report.json
```

The `continuityguard scan` step's own exit code (0 clean / 1 flagged)
gates the job directly -- no extra parsing step needed unless you want to
post a PR comment summarizing the flags, in which case parse the uploaded
JSON artifact in a following step.

## GitHub Actions -- TypeScript/npm CLI

```yaml
name: ContinuityGuard
on: [pull_request]

jobs:
  continuityguard-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: sudo apt-get update && sudo apt-get install -y ffmpeg
      - run: npm install -g continuityguard-cli
      - name: Scan generated clips
        run: continuityguard scan ./generated-clips --json --out continuityguard-report.json
```

To build from source instead (for tracking `main` rather than the
published package):

```yaml
      - uses: actions/checkout@v4
        with:
          repository: RudrenduPaul/ContinuityGuard
          path: continuityguard-src
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: sudo apt-get update && sudo apt-get install -y ffmpeg
      - run: npm ci
        working-directory: continuityguard-src
      - run: npm run build
        working-directory: continuityguard-src
      - name: Scan generated clips
        run: node continuityguard-src/dist/cli.js scan ./generated-clips --json --out continuityguard-report.json
```

## Pre-commit / local pre-push hook (Python)

For a solo creator or small studio wanting a local gate before a batch of
clips gets committed to a shared drive:

```bash
#!/usr/bin/env bash
# .git/hooks/pre-push, or wire into pre-commit via a local hook entry.
set -euo pipefail
continuityguard scan ./generated-clips
```

A non-zero exit from `continuityguard scan` (flags found, or the scan
itself failed) blocks the push. Drop `--json --out /dev/null` if you only
want the pass/fail signal and not a report file.

## Interpreting a failed gate

A non-zero exit means "worth a second look," never "confirmed defect" --
see `docs/concepts.md` for the honest limitations of both scoring passes.
A reasonable CI policy: let the gate fail the build for visibility, but
treat every flag as a manual-review queue item, not an automatic reject.
