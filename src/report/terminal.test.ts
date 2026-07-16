import { describe, it, expect } from 'vitest';
import { renderTerminalReport } from './terminal.js';
import type { ScanReport } from './types.js';

function buildReport(overrides: Partial<ScanReport> = {}): ScanReport {
  return {
    scan_id: 'cg-test',
    scanned_directory: './generated-clips',
    clips_scanned: 8,
    frames_extracted: 51,
    character_consistency: {
      characters_tracked: 3,
      similarity_threshold: 0.88,
      flagged_shots: [],
    },
    physics_plausibility: {
      discontinuity_multiplier: 3,
      flagged_shots: [],
    },
    generated_at: '2026-07-16T00:00:00.000Z',
    tool_version: '0.1.0',
    scan_duration_seconds: 0.5,
    network_calls_made: 0,
    ...overrides,
  };
}

describe('renderTerminalReport', () => {
  it('renders a clean summary with zero flags', () => {
    const output = renderTerminalReport(buildReport());
    expect(output).toContain('ContinuityGuard v0.1');
    expect(output).toContain('0 shots flagged (below 0.88 cosine threshold)');
    expect(output).toContain('0 shots flagged: no frame-to-frame motion discontinuity');
    expect(output).not.toContain('detect a physics violation');
  });

  it('renders flagged consistency and physics shots with reasons', () => {
    const output = renderTerminalReport(
      buildReport({
        character_consistency: {
          characters_tracked: 1,
          similarity_threshold: 0.88,
          flagged_shots: [
            {
              clip: 'kenji_shot02.mp4',
              character: 'kenji',
              reference_clip: 'kenji_shot01.mp4',
              similarity_score: 0.7709,
              reason: 'Cross-shot embedding similarity 0.77 is below the 0.88 threshold.',
            },
          ],
        },
        physics_plausibility: {
          discontinuity_multiplier: 3,
          flagged_shots: [
            {
              clip: 'action-discontinuity.mp4',
              frame_index_a: 4,
              frame_index_b: 5,
              discontinuity_ratio: 8.25,
              reason: 'Frame-to-frame motion discontinuity 8.2x this shot\'s local baseline.',
            },
          ],
        },
      })
    );
    expect(output).toContain('kenji_shot02.mp4');
    expect(output).toContain('similarity 0.77');
    expect(output).toContain('action-discontinuity.mp4');
    expect(output).toContain('8.25x local baseline');
  });

  it('includes the JSON report path line when provided', () => {
    const output = renderTerminalReport(buildReport(), './continuityguard-report.json');
    expect(output).toContain('Report written to ./continuityguard-report.json');
  });

  it('omits the JSON report path line when not provided', () => {
    const output = renderTerminalReport(buildReport());
    expect(output).not.toContain('Report written to');
  });
});
