#!/usr/bin/env python3
"""
CLI entry point. Wires the `scan` subcommand: CG01 ingestion -> CG02
character-consistency scoring -> CG03 physics-plausibility heuristic ->
CG04 report output (terminal by default, `--json` for machine-readable).

Console entry point: `continuityguard scan <directory> [options]`,
installed via the `continuityguard` console-script defined in
python/pyproject.toml -- the same command name as the npm CLI's `bin`
entry, so the two are drop-in equivalents on their respective toolchains.

Zero-network guarantee: nothing in this file, or anything it imports from
continuityguard.ingest or continuityguard.score, makes an outbound network
call. The only I/O is local filesystem reads/writes and spawning the local
`ffmpeg` binary via an explicit argument list (see ingest/ffmpeg.py).

Ported from src/cli.ts, which uses `commander`; this port uses the stdlib
`argparse` to avoid a CLI-framework dependency. Flags, defaults, and
messages are kept as close to the npm CLI's `--help` output and error text
as argparse's own conventions allow.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .ingest.ffmpeg import build_missing_ffmpeg_message, check_ffmpeg_available
from .report.json_report import serialize_report, write_json_report
from .report.terminal import render_terminal_report
from .scan import TOOL_VERSION, NoClipsFoundError, scan

_PROG = "continuityguard"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description=(
            "Free, local-first CLI that scores already-generated AI short-drama clips/frames "
            "for character-consistency and physics-plausibility problems. Zero network calls."
        ),
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"{_PROG} {TOOL_VERSION}"
    )

    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser(
        "scan",
        help=(
            "scan a directory of generated clips for character-consistency and "
            "physics-plausibility flags"
        ),
        description=(
            "scan a directory of generated clips for character-consistency and "
            "physics-plausibility flags"
        ),
    )
    scan_parser.add_argument("directory", help="directory of video clips to scan")
    scan_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="print the full machine-readable JSON report to stdout instead of a terminal summary",
    )
    scan_parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help="frame sample rate for ingestion (default: 2.3)",
    )
    scan_parser.add_argument(
        "--out",
        default="./continuityguard-report.json",
        help="path to write the JSON report file to",
    )

    return parser


def run_scan(directory: str, json_output: bool = False, fps: Optional[float] = None, out: str = "./continuityguard-report.json") -> int:
    """
    Runs one scan end to end and returns the process exit code (0 success,
    1 failure). Mirrors src/cli.ts's `runScan`: every failure path prints a
    clean, actionable message to stderr and returns 1, rather than letting
    a raw traceback / unhandled exception propagate.
    """
    ffmpeg_check = check_ffmpeg_available()
    if not ffmpeg_check.available:
        print(build_missing_ffmpeg_message(), file=sys.stderr)
        return 1

    target_dir = str(Path(directory).resolve())

    try:
        report = scan(directory, fps=fps)
    except FileNotFoundError:
        print(f"Directory not found: {target_dir}", file=sys.stderr)
        return 1
    except NotADirectoryError:
        print(f"Not a directory: {target_dir}", file=sys.stderr)
        return 1
    except NoClipsFoundError as error:
        # NoClipsFoundError's own message already carries the supported
        # extensions list; split across two stderr lines to match the
        # TS CLI's two separate console.error calls.
        message = str(error)
        head, _, tail = message.partition(". Supported extensions")
        print(head + ".", file=sys.stderr)
        if tail:
            print("Supported extensions" + tail, file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001 -- top-level crash guard, mirrors src/cli.ts's catch-all
        print(f"ContinuityGuard scan failed: {error}", file=sys.stderr)
        return 1

    if json_output:
        sys.stdout.write(serialize_report(report))
    else:
        # Pass the raw --out value (not pre-resolved) so write_json_report's
        # own traversal check runs against what the caller actually typed --
        # resolving here first would turn every path absolute and silently
        # bypass that check.
        write_json_report(out, report)
        out_path = str(Path(out).resolve())
        print(render_terminal_report(report, out_path))

    return 0


def run_cli(argv: List[str]) -> int:
    """`argv` follows the sys.argv convention: argv[0] is the program name,
    real arguments start at argv[1]. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv[1:])

    if args.command != "scan":
        parser.print_help()
        return 0

    return run_scan(args.directory, json_output=args.json, fps=args.fps, out=args.out)


def main() -> None:
    sys.exit(run_cli(sys.argv))


if __name__ == "__main__":
    main()
