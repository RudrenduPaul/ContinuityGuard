#!/usr/bin/env node
/**
 * CLI entry point. Wires the `scan` subcommand: CG01 ingestion -> CG02
 * character-consistency scoring -> CG03 physics-plausibility heuristic ->
 * CG04 report output (terminal by default, `--json` for machine-readable).
 *
 * Zero-network guarantee: nothing in this file, or anything it imports
 * from src/ingest or src/score, makes an outbound network call. The only
 * I/O is local filesystem reads/writes and spawning the local `ffmpeg`
 * binary. Verified by grepping the full dependency tree for fetch/http(s)/
 * axios usage -- see README "Local-only, always" for the exact commands
 * run to confirm this.
 */

import { Command } from 'commander';
import { resolve } from 'node:path';
import {
  checkFfmpegAvailable,
  buildMissingFfmpegMessage,
  extractFramesFromDirectory,
  cleanupFrames,
  listClips,
} from './ingest/ffmpeg.js';
import {
  scoreConsistency,
  CONSISTENCY_SIMILARITY_THRESHOLD,
} from './score/consistency.js';
import { scorePhysics, DISCONTINUITY_MULTIPLIER } from './score/physics.js';
import { writeJsonReport, serializeReport } from './report/json.js';
import { renderTerminalReport } from './report/terminal.js';
import type { ScanReport } from './report/types.js';

const TOOL_VERSION = '0.1.0';

export function createProgram(): Command {
  const program = new Command();
  program
    .name('continuityguard')
    .description(
      'Free, local-first CLI that scores already-generated AI short-drama clips/frames ' +
        'for character-consistency and physics-plausibility problems. Zero network calls.'
    )
    .version(TOOL_VERSION);

  program
    .command('scan')
    .argument('<directory>', 'directory of video clips to scan')
    .option('--json', 'print the full machine-readable JSON report to stdout instead of a terminal summary')
    .option('--fps <fps>', 'frame sample rate for ingestion (default: 2.3)', parseFloat)
    .option('--out <path>', 'path to write the JSON report file to', './continuityguard-report.json')
    .description('scan a directory of generated clips for character-consistency and physics-plausibility flags')
    .action(async (directory: string, options: { json?: boolean; fps?: number; out: string }) => {
      const exitCode = await runScan(directory, options);
      process.exitCode = exitCode;
    });

  return program;
}

export async function runScan(
  directory: string,
  options: { json?: boolean; fps?: number; out: string }
): Promise<number> {
  const ffmpegCheck = checkFfmpegAvailable();
  if (!ffmpegCheck.available) {
    console.error(buildMissingFfmpegMessage());
    return 1;
  }

  const targetDir = resolve(directory);
  const clips = await listClips(targetDir).catch(() => []);
  if (clips.length === 0) {
    console.error(`No supported video clips found in ${targetDir}`);
    console.error('Supported extensions: .mp4 .mov .mkv .webm .avi');
    return 1;
  }

  const startedAt = Date.now();
  const extractOptions = options.fps === undefined ? {} : { fps: options.fps };
  const extracted = await extractFramesFromDirectory(targetDir, extractOptions);

  try {
    const framesExtracted = extracted.reduce((sum, e) => sum + e.framePaths.length, 0);

    const consistencyResult = await scoreConsistency(
      extracted.map((e) => ({ clip: e.clip.name, framePaths: e.framePaths }))
    );
    const physicsResult = await scorePhysics(
      extracted.map((e) => ({ clip: e.clip.name, framePaths: e.framePaths }))
    );

    const durationSeconds = (Date.now() - startedAt) / 1000;

    const report: ScanReport = {
      scan_id: `cg-${new Date(startedAt).toISOString().replace(/[:.]/g, '-')}`,
      scanned_directory: targetDir,
      clips_scanned: clips.length,
      frames_extracted: framesExtracted,
      character_consistency: {
        characters_tracked: consistencyResult.charactersTracked,
        similarity_threshold: CONSISTENCY_SIMILARITY_THRESHOLD,
        flagged_shots: consistencyResult.flaggedShots.map((f) => ({
          clip: f.clip,
          character: f.character,
          reference_clip: f.referenceClip,
          similarity_score: f.similarityScore,
          reason: f.reason,
        })),
      },
      physics_plausibility: {
        discontinuity_multiplier: DISCONTINUITY_MULTIPLIER,
        flagged_shots: physicsResult.flaggedShots.map((f) => ({
          clip: f.clip,
          frame_index_a: f.frameIndexA,
          frame_index_b: f.frameIndexB,
          discontinuity_ratio: f.discontinuityRatio,
          reason: f.reason,
        })),
      },
      generated_at: new Date().toISOString(),
      tool_version: TOOL_VERSION,
      scan_duration_seconds: durationSeconds,
      network_calls_made: 0,
    };

    if (options.json) {
      process.stdout.write(serializeReport(report));
    } else {
      const outPath = resolve(options.out);
      await writeJsonReport(outPath, report);
      console.log(renderTerminalReport(report, outPath));
    }

    return 0;
  } finally {
    await cleanupFrames(extracted);
  }
}

/* c8 ignore start -- entrypoint guard, exercised via the built binary in
   CI/manual testing rather than the unit test suite, matching this repo's
   convention of excluding src/cli.ts's process-wiring lines from coverage
   (see vitest.config.ts) while still unit-testing runScan/createProgram
   directly. */
if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) {
  createProgram().parseAsync(process.argv);
}
/* c8 ignore stop */
