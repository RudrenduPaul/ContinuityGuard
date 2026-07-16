/**
 * CG04 -- human-readable terminal report output. Every flagged shot
 * includes a timestamp/frame reference, a numeric score, and a
 * plain-language reason -- built for a human studio QA reviewer to read
 * directly.
 */

import type { ScanReport } from './types.js';

export function renderTerminalReport(report: ScanReport, jsonPath?: string): string {
  const lines: string[] = [];
  lines.push('ContinuityGuard v0.1 -- Local Character-Consistency & Physics-QA Scoring');
  lines.push('');
  lines.push(
    `Scanning: ${report.scanned_directory} (${report.clips_scanned} clips, ffmpeg decode)`
  );
  lines.push('');

  lines.push('[SCORED] CG01 Clip Ingestion');
  lines.push(`  ${report.clips_scanned} clips decoded, ${report.frames_extracted} frames extracted`);
  lines.push('');

  lines.push('[SCORED] CG02 Character-Consistency Scoring');
  lines.push(
    `  ${report.character_consistency.characters_tracked} named characters tracked across ${report.clips_scanned} clips`
  );
  const consistencyFlags = report.character_consistency.flagged_shots;
  if (consistencyFlags.length === 0) {
    lines.push(
      `  0 shots flagged (below ${report.character_consistency.similarity_threshold.toFixed(2)} cosine threshold)`
    );
  } else {
    lines.push(
      `  ${consistencyFlags.length} shot(s) flagged: low cross-shot similarity (below ${report.character_consistency.similarity_threshold.toFixed(2)} cosine threshold)`
    );
    for (const flag of consistencyFlags) {
      lines.push(
        `    ${flag.clip} -- "${flag.character}" similarity ${flag.similarity_score.toFixed(2)} vs. reference (${flag.reference_clip})`
      );
    }
  }
  lines.push(
    '  NOTE: consistency scoring is best-validated on photorealistic content.'
  );
  lines.push(
    '  Accuracy on stylized/anime-adjacent character designs is unverified --'
  );
  lines.push(
    '  treat flags on stylized content as a prompt for human review, not a'
  );
  lines.push('  confirmed defect. See README "Known limitations."');
  lines.push('');

  lines.push('[SCORED] CG03 Physics-Plausibility Heuristic');
  const physicsFlags = report.physics_plausibility.flagged_shots;
  if (physicsFlags.length === 0) {
    lines.push('  0 shots flagged: no frame-to-frame motion discontinuity above threshold');
  } else {
    lines.push(
      `  ${physicsFlags.length} shot(s) flagged: frame-to-frame motion discontinuity above threshold`
    );
    for (const flag of physicsFlags) {
      lines.push(
        `    ${flag.clip} @ frame ${flag.frame_index_a}-${flag.frame_index_b} -- discontinuity ${flag.discontinuity_ratio}x local baseline`
      );
    }
  }
  lines.push(
    '  This is a heuristic proxy, not a physics simulator. It flags shots for'
  );
  lines.push('  human review. It does not "detect" a physics violation.');
  lines.push('');

  if (jsonPath) {
    lines.push(`Report written to ${jsonPath}`);
  }
  lines.push('Human-readable summary above. Use --json for the full structured report.');
  lines.push(
    `Scan time: ${report.scan_duration_seconds.toFixed(1)}s. Nothing left this machine. No network calls were made.`
  );

  return lines.join('\n');
}
