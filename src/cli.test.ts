import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mkdtemp, rm, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

vi.mock('./ingest/ffmpeg.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./ingest/ffmpeg.js')>();
  return { ...actual };
});

const ffmpegModule = await import('./ingest/ffmpeg.js');
const { createProgram, runScan } = await import('./cli.js');

const FIXTURE_DIR = join(import.meta.dirname, 'score', 'testdata', 'clips');

describe('createProgram', () => {
  it('registers the scan subcommand with --json/--fps/--out options', () => {
    const program = createProgram();
    expect(program.name()).toBe('continuityguard');
    const scanCommand = program.commands.find((c) => c.name() === 'scan');
    expect(scanCommand).toBeDefined();
    const optionFlags = scanCommand?.options.map((o) => o.long) ?? [];
    expect(optionFlags).toEqual(expect.arrayContaining(['--json', '--fps', '--out']));
  });

  it('reports the tool version', () => {
    const program = createProgram();
    expect(program.version()).toBe('0.1.0');
  });
});

describe('runScan', () => {
  let cwd: string;

  beforeEach(() => {
    cwd = process.cwd();
  });

  afterEach(() => {
    process.chdir(cwd);
    vi.restoreAllMocks();
  });

  it('returns exit code 1 with the install command when ffmpeg is not on PATH', async () => {
    const checkSpy = vi
      .spyOn(ffmpegModule, 'checkFfmpegAvailable')
      .mockReturnValue({ available: false });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const code = await runScan(FIXTURE_DIR, { out: './report.json' });
      expect(code).toBe(1);
      expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('ffmpeg'));
    } finally {
      checkSpy.mockRestore();
      errorSpy.mockRestore();
    }
  });

  it('returns exit code 1 and an actionable message when no clips are found', async () => {
    const emptyDir = await mkdtemp(join(tmpdir(), 'cg-empty-'));
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const code = await runScan(emptyDir, { out: './continuityguard-report.json' });
      expect(code).toBe(1);
      expect(errorSpy).toHaveBeenCalledWith(
        expect.stringContaining('No supported video clips found')
      );
    } finally {
      errorSpy.mockRestore();
      await rm(emptyDir, { recursive: true, force: true });
    }
  });

  it('scans the real committed fixtures end-to-end and writes a JSON report', async () => {
    const outDir = await mkdtemp(join(tmpdir(), 'cg-scan-out-'));
    const outPath = join(outDir, 'continuityguard-report.json');
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    try {
      const code = await runScan(FIXTURE_DIR, { out: outPath });
      expect(code).toBe(0);
      expect(logSpy).toHaveBeenCalled();

      const written = JSON.parse(await readFile(outPath, 'utf8'));
      expect(written.clips_scanned).toBe(8);
      expect(written.network_calls_made).toBe(0);
      expect(
        written.character_consistency.flagged_shots.some(
          (f: { clip: string }) => f.clip === 'kenji_shot02.mp4'
        )
      ).toBe(true);
      expect(
        written.physics_plausibility.flagged_shots.some(
          (f: { clip: string }) => f.clip === 'action-discontinuity.mp4'
        )
      ).toBe(true);
    } finally {
      logSpy.mockRestore();
      await rm(outDir, { recursive: true, force: true });
    }
  });

  it('prints the full JSON report to stdout when --json is set, without writing a file', async () => {
    const writeSpy = vi.spyOn(process.stdout, 'write').mockImplementation(() => true);
    try {
      const code = await runScan(FIXTURE_DIR, {
        json: true,
        out: './should-not-be-written.json',
      });
      expect(code).toBe(0);
      expect(writeSpy).toHaveBeenCalledTimes(1);
      const printed = JSON.parse(writeSpy.mock.calls[0]?.[0] as string);
      expect(printed.clips_scanned).toBe(8);
    } finally {
      writeSpy.mockRestore();
    }
  });

  it('returns exit code 1 with a clean error message when a clip is corrupt, instead of throwing', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'cg-corrupt-scan-'));
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      await writeFile(join(dir, 'corrupt.mp4'), 'this is not a real video file');

      // runScan must resolve (never reject) even when ffmpeg fails partway
      // through the scan -- a rejection here would surface as an unhandled
      // promise rejection at the CLI's .action() call site.
      const code = await runScan(dir, { out: join(dir, 'report.json') });

      expect(code).toBe(1);
      expect(errorSpy).toHaveBeenCalledWith(
        expect.stringContaining('ContinuityGuard scan failed')
      );
      expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('corrupt.mp4'));
    } finally {
      errorSpy.mockRestore();
      await rm(dir, { recursive: true, force: true });
    }
  });

  it('passes a custom --fps value through to frame extraction', async () => {
    const outDir = await mkdtemp(join(tmpdir(), 'cg-scan-fps-'));
    const outPath = join(outDir, 'report.json');
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    try {
      const code = await runScan(FIXTURE_DIR, { out: outPath, fps: 1 });
      expect(code).toBe(0);
      const written = JSON.parse(await readFile(outPath, 'utf8'));
      expect(written.frames_extracted).toBeGreaterThan(0);
    } finally {
      logSpy.mockRestore();
      await rm(outDir, { recursive: true, force: true });
    }
  });
});
