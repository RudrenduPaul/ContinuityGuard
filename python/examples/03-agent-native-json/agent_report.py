#!/usr/bin/env python3
"""
The agent-native use case: call ContinuityGuard in-process (no CLI
subprocess, no shelling out to `continuityguard scan`), then serialize the
structured report to JSON for a downstream tool or agent to parse. This
is exactly what continuityguard.cli does internally for `--json` mode --
shown here as a standalone, importable pattern for an agent framework's
own tool-call handler.
"""
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from continuityguard import scan_async

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "src" / "score" / "testdata" / "clips"


async def main() -> None:
    # scan_async runs the (CPU/subprocess-bound) real scan in a worker
    # thread, so it can be awaited from inside an async agent tool-call
    # handler without blocking the event loop.
    report = await scan_async(str(FIXTURE_DIR))

    payload = {
        "clips_scanned": report.clips_scanned,
        "consistency_flag_count": len(report.character_consistency.flagged_shots),
        "physics_flag_count": len(report.physics_plausibility.flagged_shots),
        "network_calls_made": report.network_calls_made,
        "full_report": asdict(report),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
