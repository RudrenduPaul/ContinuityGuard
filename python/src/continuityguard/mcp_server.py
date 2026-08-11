"""
Model Context Protocol (MCP) server for ContinuityGuard.

Exposes a single generic tool, `run`, that shells out to the real
`continuityguard` CLI (the same console script installed by this
package's `[project.scripts]` entry) and returns its result as a
structured dict. This is a thin subprocess wrapper, not a reimplementation
of the CLI's logic: the CLI stays the single source of truth for scan
behavior, and this module just gives an MCP-speaking agent (e.g. Claude
Desktop) a way to invoke it.

Every code path in the tool handler is wrapped so it can never raise:
OSError and subprocess.TimeoutExpired are caught explicitly, a non-zero
return code is surfaced as a structured `{"error": ...}` result instead of
an exception, and stdout that looks like JSON (produced by the CLI's
`--json` flag) is parsed defensively with json.JSONDecodeError caught too.

Install with the `mcp` extra and run as its own console script:

    pip install "continuityguard-cli[mcp]"
    continuityguard-mcp
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Dict, List

_PROG = "continuityguard"
_RUN_TIMEOUT_SECONDS = 300

_STATIC_HELP_FALLBACK = (
    "Run the local, zero-network ContinuityGuard CLI. Typical usage: "
    "run(['scan', '<directory>']) to scan a directory of AI-generated "
    "short-drama clips for character-consistency drift and "
    "physics-plausibility flags. Add '--json' for a machine-readable "
    "report, e.g. run(['scan', './clips', '--json'])."
)


def _cli_command() -> List[str]:
    """The subprocess argv used to invoke the real CLI, in-process Python
    guaranteed to match this package's own install (no reliance on
    `continuityguard` being resolvable on PATH)."""
    return [sys.executable, "-m", "continuityguard.cli"]


def _fetch_help_text() -> str:
    """Best-effort live `--help` output, used to populate the `run` tool's
    description dynamically at import time. Falls back to a safe static
    description if the subprocess call fails for any reason."""
    try:
        result = subprocess.run(
            _cli_command() + ["--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        help_text = (result.stdout or "").strip()
        if help_text:
            return help_text
    except (OSError, subprocess.TimeoutExpired):
        pass
    return _STATIC_HELP_FALLBACK


_HELP_TEXT = _fetch_help_text()

try:
    from mcp.server import MCPServer

    _server = MCPServer(name=_PROG)
except ImportError as exc:  # pragma: no cover - guarded by the `mcp` extra
    raise ImportError(
        "The MCP server requires the optional 'mcp' extra. "
        "Install it with: pip install \"continuityguard-cli[mcp]\""
    ) from exc


@_server.tool(
    name="run",
    description=(
        "Run the ContinuityGuard CLI with the given argument list and "
        "return its result. Equivalent to running `continuityguard "
        "<args...>` locally; nothing leaves the machine. Example: "
        "run(args=['scan', './clips', '--json']) scans a directory of "
        "clips and returns the parsed JSON report.\n\n"
        f"Real --help output:\n{_HELP_TEXT}"
    ),
)
def run(args: List[str]) -> Dict[str, Any]:
    """Shell out to the ContinuityGuard CLI and return a structured result.

    Every failure mode is caught and returned as `{"error": ...}` rather
    than raised, so this handler can never crash the MCP server process.
    """
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return {"error": "args must be a list of strings"}

    try:
        completed = subprocess.run(
            _cli_command() + args,
            capture_output=True,
            text=True,
            timeout=_RUN_TIMEOUT_SECONDS,
        )
    except OSError as exc:
        return {"error": f"failed to start continuityguard CLI: {exc}"}
    except subprocess.TimeoutExpired:
        return {
            "error": (
                f"continuityguard CLI timed out after "
                f"{_RUN_TIMEOUT_SECONDS}s"
            )
        }

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""

    if completed.returncode != 0:
        return {
            "error": f"continuityguard exited with code {completed.returncode}",
            "stdout": stdout,
            "stderr": stderr,
            "returncode": completed.returncode,
        }

    stripped = stdout.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return {"result": json.loads(stripped), "stderr": stderr}
        except json.JSONDecodeError:
            pass

    return {"stdout": stdout, "stderr": stderr, "returncode": completed.returncode}


def main() -> None:
    """Console-script entry point (`continuityguard-mcp`). Runs the MCP
    server over stdio, the transport Claude Desktop and most MCP clients
    expect by default."""
    _server.run()


if __name__ == "__main__":
    main()
