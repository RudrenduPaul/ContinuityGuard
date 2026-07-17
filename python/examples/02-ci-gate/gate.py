#!/usr/bin/env python3
"""
Using scan() as a CI gate: exit 0 when nothing is flagged, exit 1 when any
shot is flagged, so this drops directly into a CI script's pass/fail step.
Scans this repo's own bundled fixture clips (which deliberately contain
one inconsistent character pair and one motion discontinuity, so this
example demonstrates the gate failing, not just the happy path).

Usage: python3 gate.py [directory]
Exit code: 0 if no flags, 1 if any flag, 2 on a scan error (bad path,
missing ffmpeg, corrupt clip).
"""
import sys
from pathlib import Path

from continuityguard import scan
from continuityguard.scan import NoClipsFoundError

DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "src" / "score" / "testdata" / "clips"


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_DIR)

    try:
        report = scan(target)
    except (FileNotFoundError, NotADirectoryError, NoClipsFoundError, RuntimeError) as error:
        print(f"ContinuityGuard scan error: {error}", file=sys.stderr)
        return 2

    total_flags = len(report.character_consistency.flagged_shots) + len(
        report.physics_plausibility.flagged_shots
    )

    if total_flags == 0:
        print(f"PASS: {report.clips_scanned} clips scanned, 0 flags.")
        return 0

    print(f"FAIL: {total_flags} flag(s) across {report.clips_scanned} clips scanned:")
    for flag in report.character_consistency.flagged_shots:
        print(f"  [consistency] {flag.clip}: {flag.reason}")
    for flag in report.physics_plausibility.flagged_shots:
        print(f"  [physics] {flag.clip}: {flag.reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
