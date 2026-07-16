import { describe, it, expect } from 'vitest';
import { join } from 'node:path';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import {
  computeFrameDiff,
  computeDiffSequence,
  detectDiscontinuities,
  buildPhysicsReason,
  scorePhysics,
  DISCONTINUITY_MULTIPLIER,
} from './physics.js';
import { extractFrames, cleanupFrames, FRAME_BYTES } from '../ingest/ffmpeg.js';

const FIXTURE_DIR = join(import.meta.dirname, 'testdata', 'clips');

function frame(value: number, length = 12): Uint8Array {
  return new Uint8Array(length).fill(value);
}

describe('computeFrameDiff', () => {
  it('returns 0 for identical frames', () => {
    expect(computeFrameDiff(frame(100), frame(100))).toBe(0);
  });

  it('returns a normalized value in [0, 1] for maximally different frames', () => {
    expect(computeFrameDiff(frame(0), frame(255))).toBeCloseTo(1, 5);
  });

  it('scales linearly with the per-channel difference', () => {
    const diff = computeFrameDiff(frame(0), frame(51));
    expect(diff).toBeCloseTo(51 / 255, 5);
  });

  it('throws when frame sizes differ', () => {
    expect(() => computeFrameDiff(frame(0, 3), frame(0, 6))).toThrow(
      /different sizes/
    );
  });
});

describe('computeDiffSequence', () => {
  it('returns an empty array for fewer than 2 frames', () => {
    expect(computeDiffSequence([])).toEqual([]);
    expect(computeDiffSequence([frame(1)])).toEqual([]);
  });

  it('returns length-1 diffs for N frames', () => {
    const diffs = computeDiffSequence([frame(0), frame(10), frame(20)]);
    expect(diffs).toHaveLength(2);
  });
});

describe('detectDiscontinuities', () => {
  it('returns nothing for an empty diff sequence', () => {
    expect(detectDiscontinuities([])).toEqual([]);
  });

  it('flags a diff exceeding multiplier x the median baseline', () => {
    // median of [0.02, 0.02, 0.02, 0.5] is 0.02 -> ratio 25x
    const found = detectDiscontinuities([0.02, 0.02, 0.02, 0.5], 3);
    expect(found).toHaveLength(1);
    expect(found[0]?.frameIndexA).toBe(3);
    expect(found[0]?.frameIndexB).toBe(4);
    expect(found[0]?.ratio).toBeCloseTo(25, 1);
  });

  it('does not flag diffs within the local baseline', () => {
    const found = detectDiscontinuities([0.02, 0.021, 0.019, 0.022], 3);
    expect(found).toEqual([]);
  });

  it('uses the exported DISCONTINUITY_MULTIPLIER by default', () => {
    const found = detectDiscontinuities([0.01, 0.01, 0.01, 5]);
    expect(found).toHaveLength(1);
    expect(DISCONTINUITY_MULTIPLIER).toBeGreaterThan(0);
  });

  it('handles an all-zero baseline by flagging any nonzero diff', () => {
    const found = detectDiscontinuities([0, 0, 0.001, 0]);
    expect(found).toHaveLength(1);
    expect(found[0]?.baseline).toBe(0);
    expect(found[0]?.ratio).toBe(Infinity);
  });

  it('does not flag anything when baseline and all diffs are zero', () => {
    expect(detectDiscontinuities([0, 0, 0])).toEqual([]);
  });
});

describe('buildPhysicsReason', () => {
  it('never affirmatively claims to "detect" a physics violation', () => {
    const reason = buildPhysicsReason(4.2);
    expect(reason).toContain('flags the shot for');
    // The only occurrence of "detect...a physics violation" allowed is the
    // explicit negation "does not detect a physics violation" -- never an
    // affirmative "detects a physics violation" claim on its own.
    expect(reason).toMatch(/does not detect a physics violation/i);
    expect(reason.replace(/does not detect a physics violation/i, '')).not.toMatch(
      /detects? a physics violation/i
    );
    expect(reason).toContain('4.2x');
  });

  it('handles a non-finite ratio gracefully', () => {
    const reason = buildPhysicsReason(Infinity);
    expect(reason).toContain('far above');
  });
});

describe('scorePhysics', () => {
  it('flags nothing for shots with fewer than 2 frames', async () => {
    const result = await scorePhysics([{ clip: 'a.mp4', framePaths: [] }]);
    expect(result.flaggedShots).toEqual([]);
  });

  it('reports discontinuityRatio -1 for a non-finite (zero-baseline) ratio', async () => {
    // Four frames whose diff sequence is [0, 0, nonzero] -- median of that
    // sequence is 0, exercising the zero-baseline branch end-to-end through
    // scorePhysics (rather than only unit-testing detectDiscontinuities
    // directly), which is what actually writes discontinuityRatio into the
    // flagged-shot record.
    const dir = await mkdtemp(join(tmpdir(), 'cg-zero-baseline-'));
    const zero = new Uint8Array(FRAME_BYTES).fill(10);
    const different = new Uint8Array(FRAME_BYTES).fill(200);
    const paths = ['frame_0001.rgb', 'frame_0002.rgb', 'frame_0003.rgb', 'frame_0004.rgb'].map(
      (name) => join(dir, name)
    );
    await writeFile(paths[0] as string, zero);
    await writeFile(paths[1] as string, zero);
    await writeFile(paths[2] as string, zero);
    await writeFile(paths[3] as string, different);

    try {
      const result = await scorePhysics([{ clip: 'zero-baseline.mp4', framePaths: paths }]);
      expect(result.flaggedShots).toHaveLength(1);
      expect(result.flaggedShots[0]?.discontinuityRatio).toBe(-1);
      expect(result.flaggedShots[0]?.reason).toContain('far above');
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  it('flags the real action-discontinuity.mp4 fixture and not calm-baseline.mp4', async () => {
    const discontinuity = await extractFrames({
      path: join(FIXTURE_DIR, 'action-discontinuity.mp4'),
      name: 'action-discontinuity.mp4',
    });
    const calm = await extractFrames({
      path: join(FIXTURE_DIR, 'calm-baseline.mp4'),
      name: 'calm-baseline.mp4',
    });

    try {
      const result = await scorePhysics([
        { clip: discontinuity.clip.name, framePaths: discontinuity.framePaths },
        { clip: calm.clip.name, framePaths: calm.framePaths },
      ]);

      const flaggedClips = new Set(result.flaggedShots.map((f) => f.clip));
      expect(flaggedClips.has('action-discontinuity.mp4')).toBe(true);
      expect(flaggedClips.has('calm-baseline.mp4')).toBe(false);
      for (const flag of result.flaggedShots) {
        expect(flag.reason).toContain('flags the shot for');
      }
    } finally {
      await cleanupFrames([discontinuity, calm]);
    }
  });
});
