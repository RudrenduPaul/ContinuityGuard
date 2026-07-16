# Security Policy

## Supported versions

ContinuityGuard is early (v0.1.x). Only the latest published version on npm
receives security fixes.

## Reporting a vulnerability

Please report security issues privately via [GitHub Security
Advisories](https://github.com/RudrenduPaul/ContinuityGuard/security/advisories/new)
rather than a public issue. If that's not workable, open an issue with
minimal detail and ask for a private channel.

Please include:
- What you found and why it's a security concern.
- Steps to reproduce, if applicable.
- Affected version(s).

## Response

This is a small, part-time-maintained project. Best-effort response within
a few days. Confirmed vulnerabilities will get a fix and a new release; the
scope and timeline depend on severity.

## What's in scope

- Anything that would cause `continuityguard scan` to make an outbound
  network call, read/write outside the scanned directory and the report
  output path, or execute arbitrary code from clip/frame content.
- Vulnerable dependencies (`npm audit` findings at HIGH/CRITICAL severity).
- CI/CD supply-chain issues (workflow misconfiguration, unpinned actions).

## What's out of scope

- The character-consistency and physics-plausibility heuristics being
  wrong on a given clip. Those are disclosed, expected limitations (see
  README "Known limitations"), not security bugs -- please still open a
  regular issue if you find one, so the fixture set can be expanded.
