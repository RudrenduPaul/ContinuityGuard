/**
 * CG04 -- machine-readable JSON report output (`--json` mode). Built so a
 * QA agent or CI pipeline can parse scan results programmatically, with
 * the same "no bare pass/fail" guarantee as the terminal report: every
 * flagged shot carries a reason string alongside its numeric score.
 */

import { writeFile } from 'node:fs/promises';
import type { ScanReport } from './types.js';

export function serializeReport(report: ScanReport): string {
  return `${JSON.stringify(report, null, 2)}\n`;
}

export async function writeJsonReport(path: string, report: ScanReport): Promise<void> {
  await writeFile(path, serializeReport(report), 'utf8');
}

export type { ScanReport } from './types.js';
