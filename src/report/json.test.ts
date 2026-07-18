import { describe, it, expect, afterEach } from 'vitest';
import { mkdtemp, mkdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { serializeReport, writeJsonReport, UnsafeOutputPathError } from './json.js';
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
    const filePath = join(dir, 'report.json');
    try {
      const report = buildSampleReport();
      await writeJsonReport(filePath, report);
      const contents = await readFile(filePath, 'utf8');
      expect(JSON.parse(contents)).toEqual(report);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  describe('--out path safety', () => {
    let tmpDir: string;
    let originalCwd: string;

    afterEach(async () => {
      if (originalCwd) process.chdir(originalCwd);
      if (tmpDir) await rm(tmpDir, { recursive: true, force: true });
    });

    it('writes to a plain relative path within the working directory', async () => {
      tmpDir = await mkdtemp(join(tmpdir(), 'cg-out-'));
      originalCwd = process.cwd();
      process.chdir(tmpDir);

      await writeJsonReport('report.json', buildSampleReport());
      const contents = await readFile(join(tmpDir, 'report.json'), 'utf8');
      expect(JSON.parse(contents)).toEqual(buildSampleReport());
    });

    it('writes to a nested relative path within the working directory', async () => {
      tmpDir = await mkdtemp(join(tmpdir(), 'cg-out-'));
      originalCwd = process.cwd();
      process.chdir(tmpDir);
      await mkdir(join(tmpDir, 'out'));

      await writeJsonReport(join('out', 'report.json'), buildSampleReport());
      const contents = await readFile(join(tmpDir, 'out', 'report.json'), 'utf8');
      expect(JSON.parse(contents)).toEqual(buildSampleReport());
    });

    it('rejects a relative --out path that traverses outside the working directory', async () => {
      tmpDir = await mkdtemp(join(tmpdir(), 'cg-out-'));
      originalCwd = process.cwd();
      process.chdir(tmpDir);

      await expect(
        writeJsonReport(join('..', '..', 'outside-report.json'), buildSampleReport()),
      ).rejects.toThrow(UnsafeOutputPathError);
    });

    it('allows an explicit absolute --out path outside the working directory', async () => {
      tmpDir = await mkdtemp(join(tmpdir(), 'cg-out-'));
      originalCwd = process.cwd();
      process.chdir(tmpDir);

      const outsideDir = await mkdtemp(join(tmpdir(), 'cg-out-outside-'));
      const absoluteOut = join(outsideDir, 'report.json');
      try {
        await writeJsonReport(absoluteOut, buildSampleReport());
        const contents = await readFile(absoluteOut, 'utf8');
        expect(JSON.parse(contents)).toEqual(buildSampleReport());
      } finally {
        await rm(outsideDir, { recursive: true, force: true });
      }
    });
  });
});
