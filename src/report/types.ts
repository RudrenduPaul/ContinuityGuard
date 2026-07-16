/**
 * CG04 -- shared report shape consumed by both the JSON writer
 * (src/report/json.ts) and the terminal writer (src/report/terminal.ts).
 * Every flagged shot carries a timestamp/frame index, a numeric score, and
 * a plain-language reason -- never a bare pass/fail -- so a human reviewer
 * or a parsing agent knows *why* a shot was flagged.
 */

export interface ConsistencyFlagReport {
  clip: string;
  character: string;
  reference_clip: string;
  similarity_score: number;
  reason: string;
}

export interface PhysicsFlagReport {
  clip: string;
  frame_index_a: number;
  frame_index_b: number;
  discontinuity_ratio: number;
  reason: string;
}

export interface ScanReport {
  scan_id: string;
  scanned_directory: string;
  clips_scanned: number;
  frames_extracted: number;
  character_consistency: {
    characters_tracked: number;
    similarity_threshold: number;
    flagged_shots: ConsistencyFlagReport[];
  };
  physics_plausibility: {
    discontinuity_multiplier: number;
    flagged_shots: PhysicsFlagReport[];
  };
  generated_at: string;
  tool_version: string;
  scan_duration_seconds: number;
  network_calls_made: 0;
}
