/**
 * CG03 -- physics-plausibility heuristic.
 *
 * This is a frame-to-frame motion-discontinuity proxy, computed as the mean
 * absolute per-channel pixel difference between consecutive sampled frames
 * of a shot (a frame-diff proxy, not optical-flow motion-vector
 * extraction -- see README "Known limitations" for why this simpler proxy
 * was chosen for v0.1). A shot is flagged when the diff between two
 * consecutive frames exceeds a multiple of that shot's own local baseline
 * (the median frame-to-frame diff across the whole shot).
 *
 * HARD RULE, enforced everywhere this feature is surfaced (CLI output, the
 * JSON report's `reason` field, README copy): this heuristic never
 * "detects" a physics violation. It only "flags a shot for human review."
 * It has real false positives (legitimate fast motion, intentional
 * stylized jump-cuts) and false negatives (subtly implausible motion that
 * stays under the threshold) -- it is a proxy, not a ground-truth
 * validator.
 */

import { FRAME_SIZE, readRawFrame } from '../ingest/ffmpeg.js';

/**
 * A consecutive-frame diff is flagged when it exceeds this multiple of the
 * shot's own median frame-to-frame diff. Derived from this repo's own
 * fixture run -- see CHANGELOG.md "CG03 fixture calibration" entry for the
 * exact command and raw numbers this value came from, not an illustrative
 * placeholder.
 */
export const DISCONTINUITY_MULTIPLIER = 3;

/** Mean absolute per-channel pixel difference between two same-sized raw
 * RGB24 frame buffers, normalized to [0, 1]. */
export function computeFrameDiff(a: Uint8Array, b: Uint8Array): number {
  if (a.length !== b.length) {
    throw new Error('Cannot diff frames of different sizes');
  }
  let total = 0;
  for (let i = 0; i < a.length; i++) {
    total += Math.abs((a[i] as number) - (b[i] as number));
  }
  return total / a.length / 255;
}

/** Consecutive-frame diffs for an ordered sequence of frames. Length is
 * `frames.length - 1` (empty if fewer than 2 frames). */
export function computeDiffSequence(frames: Uint8Array[]): number[] {
  const diffs: number[] = [];
  for (let i = 1; i < frames.length; i++) {
    diffs.push(computeFrameDiff(frames[i - 1] as Uint8Array, frames[i] as Uint8Array));
  }
  return diffs;
}

/** Only ever called by detectDiscontinuities after it has already guarded
 * against an empty `diffs` array, so `values` is always non-empty here. */
function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? ((sorted[mid - 1] as number) + (sorted[mid] as number)) / 2
    : (sorted[mid] as number);
}

export interface Discontinuity {
  frameIndexA: number;
  frameIndexB: number;
  diff: number;
  baseline: number;
  ratio: number;
}

/**
 * Pure detection logic over an already-computed diff sequence -- split out
 * from `scorePhysics` so it has fast, deterministic unit-test coverage
 * independent of ffmpeg/frame extraction.
 */
export function detectDiscontinuities(
  diffs: number[],
  multiplier: number = DISCONTINUITY_MULTIPLIER
): Discontinuity[] {
  if (diffs.length === 0) return [];
  const baseline = median(diffs);
  const found: Discontinuity[] = [];
  diffs.forEach((diff, index) => {
    if (baseline === 0) {
      // A perfectly static baseline (e.g. an all-static shot) makes any
      // ratio computation divide-by-zero/undefined; only flag if there is
      // any motion at all against a genuinely zero baseline.
      if (diff > 0) {
        found.push({ frameIndexA: index, frameIndexB: index + 1, diff, baseline, ratio: Infinity });
      }
      return;
    }
    const ratio = diff / baseline;
    if (ratio > multiplier) {
      found.push({ frameIndexA: index, frameIndexB: index + 1, diff, baseline, ratio });
    }
  });
  return found;
}

export function buildPhysicsReason(ratio: number): string {
  const ratioText = Number.isFinite(ratio) ? `${ratio.toFixed(1)}x` : 'far above';
  return (
    `Frame-to-frame motion discontinuity ${ratioText} this shot's local baseline. ` +
    'This is a heuristic proxy, not a physics simulator -- it flags the shot for ' +
    'human review, it does not detect a physics violation. Expect both false ' +
    'positives (legitimate fast motion, stylized jump-cuts) and false negatives.'
  );
}

export interface PhysicsShotInput {
  clip: string;
  framePaths: string[];
}

export interface PhysicsFlag {
  clip: string;
  frameIndexA: number;
  frameIndexB: number;
  discontinuityRatio: number;
  reason: string;
}

export interface PhysicsResult {
  flaggedShots: PhysicsFlag[];
}

/** End-to-end CG03 entry point: reads every shot's sampled raw frames from
 * disk, computes the diff sequence, and flags discontinuities. */
export async function scorePhysics(
  shots: PhysicsShotInput[],
  options: { multiplier?: number } = {}
): Promise<PhysicsResult> {
  const flaggedShots: PhysicsFlag[] = [];
  for (const shot of shots) {
    if (shot.framePaths.length < 2) continue;
    const frames: Uint8Array[] = [];
    for (const framePath of shot.framePaths) {
      frames.push(await readRawFrame(framePath));
    }
    const diffs = computeDiffSequence(frames);
    const discontinuities = detectDiscontinuities(diffs, options.multiplier);
    for (const d of discontinuities) {
      flaggedShots.push({
        clip: shot.clip,
        frameIndexA: d.frameIndexA,
        frameIndexB: d.frameIndexB,
        discontinuityRatio: Number.isFinite(d.ratio) ? Number(d.ratio.toFixed(2)) : -1,
        reason: buildPhysicsReason(d.ratio),
      });
    }
  }
  return { flaggedShots };
}

/** Re-exported so callers (CLI, tests) can reference the expected frame
 * size without importing from src/ingest directly. */
export const EXPECTED_FRAME_SIZE = FRAME_SIZE;
