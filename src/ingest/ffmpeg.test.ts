import { describe, it, expect } from 'vitest';
import { join } from 'node:path';
import { mkdtemp, writeFile, rm, readdir, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import {
  checkFfmpegAvailable,
  detectOs,
  describeFfmpegInstallCommand,
  buildMissingFfmpegMessage,
  listClips,
  extractFrames,
  extractFramesFromDirectory,
  cleanupFrames,
  readRawFrame,
  FRAME_BYTES,
} from './ffmpeg.js';

/** Lists any leftover `continuityguard-frames-*` temp directories directly
 * under `root` -- used to prove a failed decode never leaks its temp dir. */
async function leakedFrameDirs(root: string): Promise<string[]> {
  const entries = await readdir(root, { withFileTypes: true }).catch(() => []);
  return entries
    .filter((e) => e.isDirectory() && e.name.startsWith('continuityguard-frames-'))
    .map((e) => e.name);
}

const FIXTURE_DIR = join(import.meta.dirname, '..', 'score', 'testdata', 'clips');

describe('checkFfmpegAvailable', () => {
  it('detects the real system ffmpeg install (required dev/CI dependency)', () => {
    const result = checkFfmpegAvailable();
    expect(result.available).toBe(true);
    expect(result.version).toBeTruthy();
  });
});

describe('detectOs', () => {
  it('maps darwin/win32/linux to the expected labels', () => {
    expect(detectOs('darwin')).toBe('macos');
    expect(detectOs('win32')).toBe('windows');
    expect(['debian', 'redhat']).toContain(detectOs('linux'));
  });

  it('falls back to unknown for an unrecognized platform', () => {
    expect(detectOs('sunos' as NodeJS.Platform)).toBe('unknown');
  });
});

describe('describeFfmpegInstallCommand', () => {
  it('returns a copy-pasteable command per OS', () => {
    expect(describeFfmpegInstallCommand('macos')).toContain('brew install ffmpeg');
    expect(describeFfmpegInstallCommand('debian')).toContain('apt');
    expect(describeFfmpegInstallCommand('redhat')).toContain('dnf');
    expect(describeFfmpegInstallCommand('windows')).toContain('winget');
    expect(describeFfmpegInstallCommand('unknown')).toContain('ffmpeg.org');
  });
});

describe('buildMissingFfmpegMessage', () => {
  it('includes the install command, never a raw stack trace', () => {
    const message = buildMissingFfmpegMessage('macos');
    expect(message).toContain('brew install ffmpeg');
    expect(message).not.toContain('Error:');
  });
});

describe('listClips', () => {
  it('lists only supported video extensions, sorted, non-recursive', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'cg-listclips-'));
    try {
      await writeFile(join(dir, 'b.mp4'), '');
      await writeFile(join(dir, 'a.mov'), '');
      await writeFile(join(dir, 'notes.txt'), '');
      const clips = await listClips(dir);
      expect(clips.map((c) => c.name)).toEqual(['a.mov', 'b.mp4']);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
});

describe('extractFrames + readRawFrame (real ffmpeg decode)', () => {
  it('decodes a real fixture clip into fixed-size raw RGB frames', async () => {
    const extracted = await extractFrames({
      path: join(FIXTURE_DIR, 'calm-baseline.mp4'),
      name: 'calm-baseline.mp4',
    });
    try {
      expect(extracted.framePaths.length).toBeGreaterThan(1);
      const frame = await readRawFrame(extracted.framePaths[0] as string);
      expect(frame.length).toBe(FRAME_BYTES);
    } finally {
      await cleanupFrames([extracted]);
    }
  });

  it('throws a clear error when a frame file is an unexpected size', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'cg-badframe-'));
    const badPath = join(dir, 'frame_0001.rgb');
    await writeFile(badPath, Buffer.from([1, 2, 3]));
    try {
      await expect(readRawFrame(badPath)).rejects.toThrow(/Unexpected frame size/);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  it('cleans up its own temp frame directory when ffmpeg fails to decode a corrupt clip', async () => {
    // Point os.tmpdir() (via TMPDIR) at a scratch root exclusive to this
    // test, so the "no leaked continuityguard-frames-* dir" assertion below
    // cannot be polluted by other test files' temp directories running
    // concurrently in other workers.
    const isolatedRoot = await mkdtemp(join(tmpdir(), 'cg-isolatedtmp-'));
    const originalTmpdir = process.env.TMPDIR;
    process.env.TMPDIR = isolatedRoot;
    try {
      const srcDir = await mkdtemp(join(tmpdir(), 'cg-corruptclip-src-'));
      const corruptPath = join(srcDir, 'corrupt.mp4');
      await writeFile(corruptPath, 'this is not a real video file');

      await expect(
        extractFrames({ path: corruptPath, name: 'corrupt.mp4' })
      ).rejects.toThrow(/ffmpeg exited with code/);

      expect(await leakedFrameDirs(isolatedRoot)).toEqual([]);
      await rm(srcDir, { recursive: true, force: true });
    } finally {
      if (originalTmpdir === undefined) {
        delete process.env.TMPDIR;
      } else {
        process.env.TMPDIR = originalTmpdir;
      }
      await rm(isolatedRoot, { recursive: true, force: true });
    }
  });
});

describe('extractFramesFromDirectory', () => {
  it('decodes every clip in a directory', async () => {
    const extracted = await extractFramesFromDirectory(FIXTURE_DIR);
    try {
      expect(extracted.length).toBeGreaterThanOrEqual(8);
      for (const e of extracted) {
        expect(e.framePaths.length).toBeGreaterThan(0);
      }
    } finally {
      await cleanupFrames(extracted);
    }
  });

  it('throws a clip-specific error and cleans up already-extracted temp dirs when one clip is corrupt', async () => {
    const isolatedRoot = await mkdtemp(join(tmpdir(), 'cg-isolatedtmp-'));
    const originalTmpdir = process.env.TMPDIR;
    process.env.TMPDIR = isolatedRoot;
    try {
      const dir = await mkdtemp(join(tmpdir(), 'cg-mixed-src-'));
      // A good clip that sorts before the corrupt one, so listClips's
      // deterministic name-sort order means it is fully extracted (and its
      // temp dir created) before the corrupt clip is reached in the loop.
      const goodBytes = await readFile(join(FIXTURE_DIR, 'calm-baseline.mp4'));
      await writeFile(join(dir, 'aaa_good.mp4'), goodBytes);
      await writeFile(join(dir, 'zzz_corrupt.mp4'), 'not a real video file');

      await expect(extractFramesFromDirectory(dir)).rejects.toThrow(
        /Failed to decode "zzz_corrupt\.mp4" with ffmpeg/
      );

      // Neither the good clip's temp frame dir (extracted, then cleaned up
      // when the corrupt clip failed) nor the corrupt clip's own temp dir
      // (cleaned up by extractFrames itself) should remain.
      expect(await leakedFrameDirs(isolatedRoot)).toEqual([]);
      await rm(dir, { recursive: true, force: true });
    } finally {
      if (originalTmpdir === undefined) {
        delete process.env.TMPDIR;
      } else {
        process.env.TMPDIR = originalTmpdir;
      }
      await rm(isolatedRoot, { recursive: true, force: true });
    }
  });
});
