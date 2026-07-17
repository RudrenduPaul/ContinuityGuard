"""
Top-level library entry point: CG01 ingestion -> CG02 character-consistency
scoring -> CG03 physics-plausibility heuristic -> a structured ScanReport.

This is the agent-native path: `from continuityguard import scan` gives a
CI script or an agent an in-process `ScanReport` object with no CLI
subprocess involved. `continuityguard/cli.py` is a thin argparse wrapper
around this same function, so the CLI and the library never drift.

Ported from the orchestration logic in src/cli.ts's `runScan`, split out
into its own importable module since the TypeScript CLI does not expose a
separate library entry point the way this Python port does.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .ingest.ffmpeg import (
    ExtractedFrames,
    cleanup_frames,
    extract_frames_from_directory,
    list_clips,
)
from .report.types import (
    CharacterConsistencyReport,
    ConsistencyFlagReport,
    PhysicsFlagReport,
    PhysicsPlausibilityReport,
    ScanReport,
)
from .score.consistency import CONSISTENCY_SIMILARITY_THRESHOLD, ShotInput, score_consistency
from .score.physics import DISCONTINUITY_MULTIPLIER, PhysicsShotInput, score_physics

TOOL_VERSION = "0.1.0"


class NoClipsFoundError(Exception):
    """Raised when the target directory contains no supported video clips.

    Deliberately NOT a subclass of FileNotFoundError -- the directory
    itself does exist and was read successfully; it just contains no
    supported clip files. Callers (see cli.py) need to tell this apart
    from "the directory path itself is wrong," which does raise a plain
    FileNotFoundError from list_clips().
    """


def scan(
    directory: str,
    fps: Optional[float] = None,
) -> ScanReport:
    """
    Scans a directory of generated clips for character-consistency and
    physics-plausibility flags, and returns a structured ScanReport.

    Raises FileNotFoundError if the directory does not exist,
    NotADirectoryError if the path is not a directory, NoClipsFoundError if
    the directory contains no supported clips, and RuntimeError if ffmpeg
    fails to decode a clip. Callers that want the CLI's clean
    stderr-message-plus-exit-code behavior instead of raised exceptions
    should use `continuityguard.cli.run_scan`.
    """
    target_dir = str(Path(directory).resolve())
    clips = list_clips(target_dir)
    if not clips:
        raise NoClipsFoundError(
            f"No supported video clips found in {target_dir}. "
            "Supported extensions: .mp4 .mov .mkv .webm .avi"
        )

    started_at = time.time()
    extracted: List[ExtractedFrames] = []
    try:
        extracted = extract_frames_from_directory(target_dir, fps=fps)
        frames_extracted = sum(len(e.frame_paths) for e in extracted)

        consistency_result = score_consistency(
            [ShotInput(clip=e.clip.name, frame_paths=e.frame_paths) for e in extracted]
        )
        physics_result = score_physics(
            [PhysicsShotInput(clip=e.clip.name, frame_paths=e.frame_paths) for e in extracted]
        )

        duration_seconds = time.time() - started_at
        started_dt = datetime.fromtimestamp(started_at, tz=timezone.utc)
        # Matches the TS side's `cg-${isoString.replace(/[:.]/g, '-')}`.
        started_iso = (
            started_dt.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{int(started_dt.microsecond / 1000):03d}Z"
        )
        scan_id = "cg-" + started_iso.replace(":", "-").replace(".", "-")

        report = ScanReport(
            scan_id=scan_id,
            scanned_directory=target_dir,
            clips_scanned=len(clips),
            frames_extracted=frames_extracted,
            character_consistency=CharacterConsistencyReport(
                characters_tracked=consistency_result.characters_tracked,
                similarity_threshold=CONSISTENCY_SIMILARITY_THRESHOLD,
                flagged_shots=[
                    ConsistencyFlagReport(
                        clip=f.clip,
                        character=f.character,
                        reference_clip=f.reference_clip,
                        similarity_score=f.similarity_score,
                        reason=f.reason,
                    )
                    for f in consistency_result.flagged_shots
                ],
            ),
            physics_plausibility=PhysicsPlausibilityReport(
                discontinuity_multiplier=DISCONTINUITY_MULTIPLIER,
                flagged_shots=[
                    PhysicsFlagReport(
                        clip=f.clip,
                        frame_index_a=f.frame_index_a,
                        frame_index_b=f.frame_index_b,
                        discontinuity_ratio=f.discontinuity_ratio,
                        reason=f.reason,
                    )
                    for f in physics_result.flagged_shots
                ],
            ),
            generated_at=datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            tool_version=TOOL_VERSION,
            scan_duration_seconds=duration_seconds,
            network_calls_made=0,
        )
        return report
    finally:
        cleanup_frames(extracted)


async def scan_async(directory: str, fps: Optional[float] = None) -> ScanReport:
    """Async wrapper around `scan`, run in a thread so it does not block an
    event loop -- useful for callers already inside `asyncio` (e.g. an
    agent framework's async tool-call handler). ffmpeg decode and ONNX
    inference are both CPU/subprocess-bound work, not natively async, so
    this offloads to a worker thread rather than reimplementing an async
    ffmpeg/onnxruntime pipeline."""
    import asyncio

    return await asyncio.to_thread(scan, directory, fps)
