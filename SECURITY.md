# Security Policy

## Supported versions

ContinuityGuard is early (v0.1.x) and pre-1.0. Only the latest published
version of each distribution receives security fixes.

| Package | Version | Supported |
| --- | --- | --- |
| `continuityguard-cli` (PyPI) | 0.1.x | Yes |
| `continuityguard-cli` (npm) | -- | Not yet published to the npm registry as of this writing; see the root README's "Install" section. |

## Reporting a vulnerability

Please report security issues privately via [GitHub Security
Advisories](https://github.com/RudrenduPaul/ContinuityGuard/security/advisories/new)
rather than a public issue. If that's not workable, open an issue with
minimal detail and ask for a private channel.

Please include:
- Which distribution is affected (PyPI package, npm source, or both).
- What you found and why it's a security concern.
- Steps to reproduce, if applicable.
- Affected version(s).

## Response

This is a small, part-time-maintained project. Best-effort response within
a few days. Confirmed vulnerabilities will get a fix and a new release; the
scope and timeline depend on severity.

## What's in scope

- Anything that would cause `continuityguard scan` (either distribution)
  to make an outbound network call, read/write outside the scanned
  directory and the report output path, or execute arbitrary code from
  clip/frame content.
- Any ffmpeg subprocess invocation constructed in a way that lets a
  crafted clip path or filename escape argument-list execution (e.g. shell
  interpretation of a filename). Both CLIs invoke ffmpeg with an explicit
  argument list, never a shell string; a path where user-controlled input
  reaches a shell is a real bug, not a theoretical one.
- Vulnerable dependencies (`npm audit` / `pip-audit` findings at
  HIGH/CRITICAL severity).
- CI/CD supply-chain issues (workflow misconfiguration, unpinned actions).

## What's out of scope

- The character-consistency and physics-plausibility heuristics being
  wrong on a given clip. Those are disclosed, expected limitations (see
  README "Known limitations"), not security bugs -- please still open a
  regular issue if you find one, so the fixture set can be expanded.
