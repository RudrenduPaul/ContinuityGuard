/**
 * CG04 -- machine-readable JSON report output (`--json` mode). Built so a
 * QA agent or CI pipeline can parse scan results programmatically, with
 * the same "no bare pass/fail" guarantee as the terminal report: every
 * flagged shot carries a reason string alongside its numeric score.
 */

import { writeFile } from 'node:fs/promises';
import * as nodePath from 'node:path';
import type { ScanReport } from './types.js';

export class UnsafeOutputPathError extends Error {}

// --out is a plain CLI flag today, but this CLI is also meant to be invoked
// programmatically by agents that may derive the value from less-trusted
// input. A relative path containing `..` segments can escape the intended
// output location entirely (`--out ../../../etc/cron.d/x`) -- reject any
// --out value that resolves outside the current working directory. An
// explicit absolute path is still allowed: that's a value the caller
// typed/passed directly, not one that silently escaped via traversal.
function assertSafeOutputPath(filePath: string): void {
  if (nodePath.isAbsolute(filePath)) return;
  const cwd = process.cwd();
  const resolved = nodePath.resolve(cwd, filePath);
  if (resolved !== cwd && !resolved.startsWith(cwd + nodePath.sep)) {
    throw new UnsafeOutputPathError(
      `--out "${filePath}" resolves outside the current working directory (${resolved}). ` +
        'Pass an absolute path if you intend to write outside the working directory.',
    );
  }
}

export function serializeReport(report: ScanReport): string {
  return `${JSON.stringify(report, null, 2)}\n`;
}

export async function writeJsonReport(path: string, report: ScanReport): Promise<void> {
  assertSafeOutputPath(path);
  await writeFile(path, serializeReport(report), 'utf8');
}

export type { ScanReport } from './types.js';
