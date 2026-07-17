#!/usr/bin/env python3
"""
The core library call: scan() a directory of clips and read back the
structured ScanReport. Scans this repo's own bundled fixture clips, so it
runs with no setup beyond `pip install -e .` and a system ffmpeg install.
"""
from pathlib import Path

from continuityguard import scan

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "src" / "score" / "testdata" / "clips"


def main() -> None:
    report = scan(str(FIXTURE_DIR))

    print(f"Scanned {report.clips_scanned} clips, {report.frames_extracted} frames extracted.")
    print(f"Characters tracked: {report.character_consistency.characters_tracked}")

    if report.character_consistency.flagged_shots:
        print(f"\n{len(report.character_consistency.flagged_shots)} consistency flag(s):")
        for flag in report.character_consistency.flagged_shots:
            print(f"  {flag.clip}: similarity {flag.similarity_score:.2f} vs. {flag.reference_clip}")
    else:
        print("\nNo character-consistency flags.")

    if report.physics_plausibility.flagged_shots:
        print(f"\n{len(report.physics_plausibility.flagged_shots)} physics-plausibility flag(s):")
        for flag in report.physics_plausibility.flagged_shots:
            print(
                f"  {flag.clip} @ frame {flag.frame_index_a}-{flag.frame_index_b}: "
                f"{flag.discontinuity_ratio}x baseline"
            )
    else:
        print("\nNo physics-plausibility flags.")

    print(f"\nScan took {report.scan_duration_seconds:.2f}s. Network calls made: {report.network_calls_made}.")


if __name__ == "__main__":
    main()
