/**
 * CG01 -- clip/frame ingestion.
 *
 * ContinuityGuard depends on a system `ffmpeg` install rather than bundling a
 * static per-platform binary in v0.1. A static ffmpeg build is materially
 * larger than this repo's own dependency footprint (commonly 50-80MB+ per
 * platform depending on included codecs) and ffmpeg's licensing terms shift
 * between LGPL and GPL depending on which codecs/filters are compiled in --
 * a real legal-review cost this project is not taking on before there is
 * evidence anyone is using the tool. ffmpeg is a near-ubiquitous developer
 * tool already (commonly pre-installed, or one `brew install ffmpeg` /
 * `apt install ffmpeg` away), so this keeps the npm package small and its
 * own licensing surface simple: ContinuityGuard's code never redistributes
 * ffmpeg binaries or inherits their licensing obligations.
 *
 * The real cost of this choice: a user without ffmpeg installed hits a real
 * setup step before their first `scan` succeeds. `checkFfmpegAvailable` and
 * `describeFfmpegInstallCommand` exist so that failure is a clear, actionable
 * one-line message -- never a raw ENOENT stack trace.
 */

import { spawn, spawnSync } from 'node:child_process';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export interface FfmpegCheckResult {
  available: boolean;
  version?: string | undefined;
}

/** Frame sample rate used for CG01 decode -- 2.3 fps, matching the plan's
 * "roughly 2-3 fps sample rate is fine" guidance for shot-level QA sampling. */
export const DEFAULT_SAMPLE_FPS = 2.3;

/**
 * Frames are decoded to headerless raw RGB24 at a fixed square size rather
 * than PNG. This is a deliberate simplification: it lets both scoring
 * modules (consistency.ts, physics.ts) read a frame as a fixed-length
 * Uint8Array with zero image-decoding dependency, instead of pulling in a
 * PNG parser just to get back to raw pixels a moment later. The fixed
 * 224x224 size also matches the embedding model's expected input
 * dimensions (see src/score/consistency.ts), so one decode pass serves
 * both scoring paths.
 */
export const FRAME_SIZE = 224;
export const FRAME_BYTES = FRAME_SIZE * FRAME_SIZE * 3;

const SUPPORTED_CLIP_EXTENSIONS = new Set(['.mp4', '.mov', '.mkv', '.webm', '.avi']);

/**
 * Checks whether `ffmpeg` is reachable on PATH. Never throws -- callers use
 * the boolean result to decide whether to continue or print an install
 * command and exit.
 */
export function checkFfmpegAvailable(): FfmpegCheckResult {
  const result = spawnSync('ffmpeg', ['-version'], { encoding: 'utf8' });
  if (result.error || result.status !== 0) {
    return { available: false };
  }
  const firstLine = result.stdout.split('\n')[0] ?? '';
  const match = /ffmpeg version (\S+)/.exec(firstLine);
  return { available: true, version: match?.[1] };
}

export type DetectedOs = 'macos' | 'debian' | 'redhat' | 'windows' | 'unknown';

export function detectOs(platform: NodeJS.Platform = process.platform): DetectedOs {
  if (platform === 'darwin') return 'macos';
  if (platform === 'win32') return 'windows';
  if (platform === 'linux') {
    // Best-effort: prefer apt (Debian/Ubuntu) as the more common default;
    // callers on an RPM-based distro can still read the apt command and
    // translate it, but we try a quick, cheap heuristic first.
    const hasAptCheck = spawnSync('sh', ['-c', 'command -v apt-get'], { encoding: 'utf8' });
    if (hasAptCheck.status === 0) return 'debian';
    const hasDnfCheck = spawnSync('sh', ['-c', 'command -v dnf || command -v yum'], {
      encoding: 'utf8',
    });
    if (hasDnfCheck.status === 0) return 'redhat';
    return 'debian';
  }
  return 'unknown';
}

/** Returns the exact, copy-pasteable install command for the detected OS. */
export function describeFfmpegInstallCommand(os: DetectedOs = detectOs()): string {
  switch (os) {
    case 'macos':
      return 'brew install ffmpeg';
    case 'debian':
      return 'sudo apt update && sudo apt install -y ffmpeg';
    case 'redhat':
      return 'sudo dnf install -y ffmpeg';
    case 'windows':
      return 'winget install ffmpeg (or: choco install ffmpeg)';
    case 'unknown':
    default:
      return 'install ffmpeg via your OS package manager, or see https://ffmpeg.org/download.html';
  }
}

export function buildMissingFfmpegMessage(os: DetectedOs = detectOs()): string {
  return [
    'ContinuityGuard requires ffmpeg, and it was not found on PATH.',
    `Install it with:  ${describeFfmpegInstallCommand(os)}`,
    'Then re-run your scan. ContinuityGuard never bundles ffmpeg itself --',
    'see README "Requirements" for why.',
  ].join('\n');
}

export interface ClipInfo {
  path: string;
  name: string;
}

/** Lists clip files (by extension) directly inside a directory, sorted for
 * deterministic scan ordering. Does not recurse into subdirectories. */
export async function listClips(directory: string): Promise<ClipInfo[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && SUPPORTED_CLIP_EXTENSIONS.has(extname(entry.name)))
    .map((entry) => ({ path: join(directory, entry.name), name: entry.name }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function extname(name: string): string {
  const idx = name.lastIndexOf('.');
  return idx === -1 ? '' : name.slice(idx).toLowerCase();
}

export interface ExtractedFrames {
  clip: ClipInfo;
  frameDir: string;
  /** Paths to headerless raw RGB24 frame files, FRAME_SIZE x FRAME_SIZE,
   * in temporal order. Read with `readRawFrame`. */
  framePaths: string[];
}

/**
 * Decodes a single clip into sampled raw RGB24 frames via ffmpeg, at
 * `DEFAULT_SAMPLE_FPS` unless overridden. Frames are written to a fresh
 * temp directory the caller is responsible for cleaning up (or use
 * `extractFramesFromDirectory`, which cleans up automatically).
 *
 * If ffmpeg fails (a corrupt file, an unsupported codec, a zero-byte
 * file, etc.) and this call created its own temp directory (no `workDir`
 * override was passed in), that now-orphaned temp directory is removed
 * before the error is re-thrown, rather than left behind on disk.
 */
export async function extractFrames(
  clip: ClipInfo,
  options: { fps?: number; workDir?: string } = {}
): Promise<ExtractedFrames> {
  const fps = options.fps ?? DEFAULT_SAMPLE_FPS;
  const ownsFrameDir = options.workDir === undefined;
  const frameDir =
    options.workDir ?? (await mkdtemp(join(tmpdir(), 'continuityguard-frames-')));

  try {
    await runFfmpeg([
      '-y',
      '-i',
      clip.path,
      '-vf',
      `fps=${fps},scale=${FRAME_SIZE}:${FRAME_SIZE}`,
      '-c:v',
      'rawvideo',
      '-pix_fmt',
      'rgb24',
      '-f',
      'image2',
      '-loglevel',
      'error',
      join(frameDir, 'frame_%04d.rgb'),
    ]);

    const entries = await readdir(frameDir);
    const framePaths = entries
      .filter((entry) => entry.startsWith('frame_') && entry.endsWith('.rgb'))
      .sort()
      .map((entry) => join(frameDir, entry));

    return { clip, frameDir, framePaths };
  } catch (error) {
    if (ownsFrameDir) {
      await rm(frameDir, { recursive: true, force: true });
    }
    throw error;
  }
}

/**
 * Decodes every clip in a directory into sampled frames. Returns one
 * `ExtractedFrames` entry per clip. Callers should call `cleanupFrames` when
 * done to remove the temp directories.
 *
 * If ffmpeg fails to decode any single clip (a corrupt file, an unsupported
 * codec, a zero-byte file, etc.), this throws a clear error naming the
 * offending clip -- rather than letting a raw ffmpeg stderr dump propagate
 * as an unhandled rejection -- and first cleans up the temp frame
 * directories already created for clips that decoded successfully earlier
 * in the loop, so one bad clip in a batch never leaks temp storage.
 */
export async function extractFramesFromDirectory(
  directory: string,
  options: { fps?: number } = {}
): Promise<ExtractedFrames[]> {
  const clips = await listClips(directory);
  const results: ExtractedFrames[] = [];
  for (const clip of clips) {
    try {
      results.push(await extractFrames(clip, options));
    } catch (error) {
      await cleanupFrames(results);
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Failed to decode "${clip.name}" with ffmpeg: ${message}`, { cause: error });
    }
  }
  return results;
}

/** Reads a headerless raw RGB24 frame file back into a Uint8Array of
 * length FRAME_BYTES (FRAME_SIZE * FRAME_SIZE * 3, row-major, RGB). */
export async function readRawFrame(framePath: string): Promise<Uint8Array> {
  const buffer = await readFile(framePath);
  if (buffer.byteLength !== FRAME_BYTES) {
    throw new Error(
      `Unexpected frame size for ${framePath}: got ${buffer.byteLength} bytes, expected ${FRAME_BYTES}`
    );
  }
  return new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength);
}

export async function cleanupFrames(extracted: ExtractedFrames[]): Promise<void> {
  await Promise.all(
    extracted.map((e) => rm(e.frameDir, { recursive: true, force: true }))
  );
}

function runFfmpeg(args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn('ffmpeg', args, { stdio: ['ignore', 'ignore', 'pipe'] });
    let stderr = '';
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`ffmpeg exited with code ${code}: ${stderr.trim()}`));
      }
    });
  });
}
