"""
CG04 -- human-readable terminal report output. Every flagged shot
includes a timestamp/frame reference, a numeric score, and a
plain-language reason -- built for a human studio QA reviewer to read
directly.

Ported line-for-line from src/report/terminal.ts so the two CLIs print
matching output.
"""
from __future__ import annotations

from typing import List, Optional

from .types import ScanReport


def render_terminal_report(report: ScanReport, json_path: Optional[str] = None) -> str:
    lines: List[str] = []
    lines.append("ContinuityGuard v0.1 -- Local Character-Consistency & Physics-QA Scoring")
    lines.append("")
    lines.append(
        f"Scanning: {report.scanned_directory} ({report.clips_scanned} clips, ffmpeg decode)"
    )
    lines.append("")

    lines.append("[SCORED] CG01 Clip Ingestion")
    lines.append(
        f"  {report.clips_scanned} clips decoded, {report.frames_extracted} frames extracted"
    )
    lines.append("")

    lines.append("[SCORED] CG02 Character-Consistency Scoring")
    lines.append(
        f"  {report.character_consistency.characters_tracked} named characters tracked "
        f"across {report.clips_scanned} clips"
    )
    consistency_flags = report.character_consistency.flagged_shots
    if not consistency_flags:
        lines.append(
            f"  0 shots flagged (below "
            f"{report.character_consistency.similarity_threshold:.2f} cosine threshold)"
        )
    else:
        lines.append(
            f"  {len(consistency_flags)} shot(s) flagged: low cross-shot similarity "
            f"(below {report.character_consistency.similarity_threshold:.2f} cosine threshold)"
        )
        for flag in consistency_flags:
            lines.append(
                f'    {flag.clip} -- "{flag.character}" similarity '
                f"{flag.similarity_score:.2f} vs. reference ({flag.reference_clip})"
            )
    lines.append("  NOTE: consistency scoring is best-validated on photorealistic content.")
    lines.append("  Accuracy on stylized/anime-adjacent character designs is unverified --")
    lines.append("  treat flags on stylized content as a prompt for human review, not a")
    lines.append('  confirmed defect. See README "Known limitations."')
    lines.append("")

    lines.append("[SCORED] CG03 Physics-Plausibility Heuristic")
    physics_flags = report.physics_plausibility.flagged_shots
    if not physics_flags:
        lines.append("  0 shots flagged: no frame-to-frame motion discontinuity above threshold")
    else:
        lines.append(
            f"  {len(physics_flags)} shot(s) flagged: frame-to-frame motion discontinuity "
            f"above threshold"
        )
        for flag in physics_flags:
            lines.append(
                f"    {flag.clip} @ frame {flag.frame_index_a}-{flag.frame_index_b} -- "
                f"discontinuity {flag.discontinuity_ratio}x local baseline"
            )
    lines.append("  This is a heuristic proxy, not a physics simulator. It flags shots for")
    lines.append('  human review. It does not "detect" a physics violation.')
    lines.append("")

    if json_path:
        lines.append(f"Report written to {json_path}")
    lines.append("Human-readable summary above. Use --json for the full structured report.")
    lines.append(
        f"Scan time: {report.scan_duration_seconds:.1f}s. Nothing left this machine. "
        f"No network calls were made."
    )

    return "\n".join(lines)
