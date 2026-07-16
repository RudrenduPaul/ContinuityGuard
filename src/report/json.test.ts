import { describe, it, expect } from 'vitest';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { serializeReport, writeJsonReport } from './json.js';
import type { ScanReport } from './types.js';

function buildSampleReport(): ScanReport {
  return {
    scan_id: 'cg-test',
    scanned_directory: '/tmp/clips',
    clips_scanned: 2,
    frames_extracted: 10,
    character_consistency: {
      characters_tracked: 1,
      similarity_threshold: 0.88,
      flagged_shots: [],
    },
    physics_plausibility: {
      discontinuity_multiplier: 3,
      flagged_shots: [],
    },
    generated_at: '2026-07-16T00:00:00.000Z',
    tool_version: '0.1.0',
    scan_duration_seconds: 1.23,
    network_calls_made: 0,
  };
}

describe('serializeReport', () => {
  it('produces valid, pretty-printed, newline-terminated JSON', () => {
    const report = buildSampleReport();
    const serialized = serializeReport(report);
    expect(serialized.endsWith('\n')).toBe(true);
    expect(JSON.parse(serialized)).toEqual(report);
  });
});

describe('writeJsonReport', () => {
  it('writes the serialized report to disk', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'cg-json-report-'));
    const path = join(dir, 'report.json');
    try {
      const report = buildSampleReport();
      await writeJsonReport(path, report);
      const contents = await readFile(path, 'utf8');
      expect(JSON.parse(contents)).toEqual(report);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
});
