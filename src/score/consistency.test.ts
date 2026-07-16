import { describe, it, expect } from 'vitest';
import { join } from 'node:path';
import type * as ort from 'onnxruntime-node';
import {
  cosineSimilarity,
  parseCharacterName,
  flagInconsistentShots,
  buildConsistencyReason,
  scoreConsistency,
  preprocessFrame,
  embedFrame,
  embedShot,
  CONSISTENCY_SIMILARITY_THRESHOLD,
} from './consistency.js';
import { extractFrames, cleanupFrames, FRAME_SIZE } from '../ingest/ffmpeg.js';

function fakeSession(overrides: Partial<ort.InferenceSession>): ort.InferenceSession {
  return {
    inputNames: ['input'],
    outputNames: ['output'],
    run: async () => ({
      output: { data: new Float32Array([1, 2, 3]) },
    }),
    ...overrides,
  } as unknown as ort.InferenceSession;
}

const FIXTURE_DIR = join(import.meta.dirname, 'testdata', 'clips');

describe('cosineSimilarity', () => {
  it('returns 1 for identical vectors', () => {
    const v = new Float32Array([1, 2, 3]);
    expect(cosineSimilarity(v, v)).toBeCloseTo(1, 5);
  });

  it('returns 0 for orthogonal vectors', () => {
    expect(cosineSimilarity(new Float32Array([1, 0]), new Float32Array([0, 1]))).toBeCloseTo(
      0,
      5
    );
  });

  it('returns -1 for opposite vectors', () => {
    expect(
      cosineSimilarity(new Float32Array([1, 0]), new Float32Array([-1, 0]))
    ).toBeCloseTo(-1, 5);
  });

  it('returns 0 when either vector is all-zero', () => {
    expect(cosineSimilarity(new Float32Array([0, 0]), new Float32Array([1, 2]))).toBe(0);
  });

  it('throws on dimension mismatch', () => {
    expect(() =>
      cosineSimilarity(new Float32Array([1]), new Float32Array([1, 2]))
    ).toThrow(/dimensionality/);
  });
});

describe('parseCharacterName', () => {
  it('extracts the character name before the first underscore', () => {
    expect(parseCharacterName('mei_shot01.mp4')).toBe('mei');
    expect(parseCharacterName('Kenji_shot02.mov')).toBe('kenji');
  });

  it('returns undefined for filenames with no matching convention', () => {
    expect(parseCharacterName('action-discontinuity.mp4')).toBeUndefined();
    expect(parseCharacterName('random.mp4')).toBeUndefined();
  });
});

describe('preprocessFrame', () => {
  it('produces a CHW float32 array of the expected length', () => {
    const raw = new Uint8Array(FRAME_SIZE * FRAME_SIZE * 3).fill(128);
    const out = preprocessFrame(raw);
    expect(out.length).toBe(3 * FRAME_SIZE * FRAME_SIZE);
  });
});

describe('embedFrame error handling against a malformed session', () => {
  const raw = new Uint8Array(FRAME_SIZE * FRAME_SIZE * 3).fill(64);

  it('throws when the model exposes no input tensor names', async () => {
    const session = fakeSession({ inputNames: [] });
    await expect(embedFrame(raw, session)).rejects.toThrow(/no input tensor names/);
  });

  it('throws when the model exposes no output tensor names', async () => {
    const session = fakeSession({ outputNames: [] });
    await expect(embedFrame(raw, session)).rejects.toThrow(/no output tensor names/);
  });

  it('throws when the model produces no output tensor for the named output', async () => {
    const session = fakeSession({ run: async () => ({}) });
    await expect(embedFrame(raw, session)).rejects.toThrow(/produced no output tensor/);
  });

  it('returns the raw output vector on a well-formed session', async () => {
    const session = fakeSession({});
    const embedding = await embedFrame(raw, session);
    expect(Array.from(embedding)).toEqual([1, 2, 3]);
  });
});

describe('embedShot', () => {
  it('throws when given zero frame paths', async () => {
    await expect(embedShot([], fakeSession({}))).rejects.toThrow(
      /zero extracted frames/
    );
  });
});

describe('buildConsistencyReason', () => {
  it('always discloses the photorealistic-only validation limitation', () => {
    const reason = buildConsistencyReason(0.5);
    expect(reason).toMatch(/photorealistic/i);
    expect(reason).toMatch(/unverified/i);
    expect(reason).toContain(CONSISTENCY_SIMILARITY_THRESHOLD.toFixed(2));
  });
});

describe('flagInconsistentShots', () => {
  function embed(...values: number[]): Float32Array {
    return new Float32Array(values);
  }

  it('flags a shot below threshold against its character reference', () => {
    const result = flagInconsistentShots(
      [
        { clip: 'mei_shot01.mp4', embedding: embed(1, 0, 0) },
        { clip: 'mei_shot02.mp4', embedding: embed(0, 1, 0) },
      ],
      0.5
    );
    expect(result.charactersTracked).toBe(1);
    expect(result.flaggedShots).toHaveLength(1);
    expect(result.flaggedShots[0]?.clip).toBe('mei_shot02.mp4');
    expect(result.flaggedShots[0]?.referenceClip).toBe('mei_shot01.mp4');
  });

  it('does not flag a shot at or above threshold', () => {
    const result = flagInconsistentShots(
      [
        { clip: 'mei_shot01.mp4', embedding: embed(1, 0, 0) },
        { clip: 'mei_shot02.mp4', embedding: embed(1, 0, 0) },
      ],
      0.99
    );
    expect(result.flaggedShots).toEqual([]);
  });

  it('skips clips whose filename does not match the character convention', () => {
    const result = flagInconsistentShots([
      { clip: 'random.mp4', embedding: embed(1, 0, 0) },
      { clip: 'other.mp4', embedding: embed(0, 1, 0) },
    ]);
    expect(result.charactersTracked).toBe(0);
    expect(result.flaggedShots).toEqual([]);
  });

  it('does not compare a character with only one shot', () => {
    const result = flagInconsistentShots([
      { clip: 'mei_shot01.mp4', embedding: embed(1, 0, 0) },
    ]);
    expect(result.charactersTracked).toBe(1);
    expect(result.flaggedShots).toEqual([]);
  });

  it('compares every later shot to the first-seen reference shot for that character', () => {
    const result = flagInconsistentShots(
      [
        { clip: 'mei_shot01.mp4', embedding: embed(1, 0, 0) },
        { clip: 'mei_shot02.mp4', embedding: embed(1, 0, 0) },
        { clip: 'mei_shot03.mp4', embedding: embed(0, 1, 0) },
      ],
      0.5
    );
    expect(result.flaggedShots).toHaveLength(1);
    expect(result.flaggedShots[0]?.clip).toBe('mei_shot03.mp4');
  });
});

describe('scoreConsistency (real ONNX inference against committed fixtures)', () => {
  it('does not flag the real mei_shot01/mei_shot02 consistent pair', async () => {
    const shot1 = await extractFrames({
      path: join(FIXTURE_DIR, 'mei_shot01.mp4'),
      name: 'mei_shot01.mp4',
    });
    const shot2 = await extractFrames({
      path: join(FIXTURE_DIR, 'mei_shot02.mp4'),
      name: 'mei_shot02.mp4',
    });
    try {
      const result = await scoreConsistency([
        { clip: shot1.clip.name, framePaths: shot1.framePaths },
        { clip: shot2.clip.name, framePaths: shot2.framePaths },
      ]);
      expect(result.flaggedShots).toEqual([]);
    } finally {
      await cleanupFrames([shot1, shot2]);
    }
  });

  it('flags the real kenji_shot01/kenji_shot02 deliberately-inconsistent pair', async () => {
    const shot1 = await extractFrames({
      path: join(FIXTURE_DIR, 'kenji_shot01.mp4'),
      name: 'kenji_shot01.mp4',
    });
    const shot2 = await extractFrames({
      path: join(FIXTURE_DIR, 'kenji_shot02.mp4'),
      name: 'kenji_shot02.mp4',
    });
    try {
      const result = await scoreConsistency([
        { clip: shot1.clip.name, framePaths: shot1.framePaths },
        { clip: shot2.clip.name, framePaths: shot2.framePaths },
      ]);
      expect(result.flaggedShots).toHaveLength(1);
      expect(result.flaggedShots[0]?.clip).toBe('kenji_shot02.mp4');
      expect(result.flaggedShots[0]?.similarityScore).toBeLessThan(
        CONSISTENCY_SIMILARITY_THRESHOLD
      );
    } finally {
      await cleanupFrames([shot1, shot2]);
    }
  });
});
