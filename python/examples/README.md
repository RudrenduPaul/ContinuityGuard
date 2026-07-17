# Python examples

Each numbered subdirectory is a real, runnable script against the actual
`continuityguard` Python library (`from continuityguard import scan`), not
pseudocode. They scan this repo's own bundled fixture clips under
`../../src/score/testdata/clips/`, so nothing external is required beyond
a system `ffmpeg` install.

Install the package first (editable install from this checkout, or `pip
install continuityguard-cli` from PyPI both work identically):

```bash
cd python
pip install -e .
```

Then run any example directly:

```bash
python3 examples/01-basic-scan/scan.py
python3 examples/02-ci-gate/gate.py
python3 examples/03-agent-native-json/agent_report.py
```

| Example | What it demonstrates |
| --- | --- |
| [01-basic-scan](./01-basic-scan/) | The core library call: `scan()`, reading back `character_consistency`/`physics_plausibility`, printing a human-readable summary. |
| [02-ci-gate](./02-ci-gate/) | Using `scan()` as a CI gate: fail the process (non-zero exit) if any shot is flagged, suitable to drop into a CI script directly. |
| [03-agent-native-json](./03-agent-native-json/) | The agent-native use case: calling ContinuityGuard in-process (no CLI subprocess), serializing the structured report to JSON for a downstream tool or agent to parse. |
