/**
 * Response shapes from the CERNAL API.
 *
 * Mirrors src/api/schemas.py. The authoritative machine-readable version is at
 * /api/openapi.json — regenerate from there if these drift.
 */

export type RunStatus = "DRAFT" | "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
export type InputMode = "de" | "direct";
export type ValidationStatus = "PENDING" | "VALID" | "INVALID";
export type MetricDirection = "HIGHER_BETTER" | "LOWER_BETTER";
export type DecisionTag = "NONE" | "PINNED" | "SHORTLISTED" | "REJECTED" | "SYNTHESIZE";

export const TERMINAL_STATUSES: readonly RunStatus[] = ["COMPLETED", "FAILED", "CANCELLED"];
export const isTerminal = (status: RunStatus) => TERMINAL_STATUSES.includes(status);

export interface User {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
}

export interface Registration {
  username: string;
  email: string;
  pending_approval: boolean;
  message: string;
}

export interface GateFamily {
  name: string;
  label: string;
  description: string;
  /** False for mechanisms that are designed but not yet implemented. */
  available: boolean;
}

export interface Version {
  app_version: string;
  api_schema_version: string;
  engine: string;
  engine_version: string;
  engine_schema_version: string;
  gate_families: GateFamily[];
  scoring_profiles: string[];
}

export interface Project {
  id: string;
  name: string;
  organism: string;
  biological_objective: string;
  dataset_count: number;
  run_count: number;
  created_at: string;
  updated_at: string;
}

export interface ExampleDataset {
  key: string;
  label: string;
  description: string;
}

export interface ValidationReport {
  rows: number;
  columns: string[];
  detected_columns?: Record<string, string>;
  errors: string[];
  warnings: string[];
}

export interface Dataset {
  id: string;
  project_id: string;
  name: string;
  filename: string;
  checksum_sha256: string;
  size_bytes: number;
  schema_version: string;
  validation_status: ValidationStatus;
  validation_report: ValidationReport;
  created_at: string;
}

export interface RunCounts {
  candidates: number;
  artifacts: number;
}

/** The polling response. Deliberately cheap — no joins across candidates. */
export interface RunStatusResponse {
  id: string;
  status: RunStatus;
  stage: string;
  progress_pct: number;
  error_summary: string | null;
  warnings: string[];
  submitted_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  counts: RunCounts;
}

export interface Run {
  id: string;
  project_id: string;
  dataset_id: string | null;
  status: RunStatus;
  stage: string;
  progress_pct: number;
  input_mode: InputMode;
  trigger_sequence: string;
  gate_families: string[];
  scoring_profile: string;
  seed: number | null;
  params_snapshot: RunParams;
  engine_version: string;
  error_summary: string;
  warnings: string[];
  cancel_requested: boolean;
  submitted_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface Metric {
  name: string;
  raw_value: number | null;
  normalized_value: number | null;
  weight: number;
  direction: MetricDirection;
}

export interface PlasmidSegment {
  kind: "promoter" | "switch" | "payload" | "marker" | "terminator" | "backbone";
  name: string;
  length_bp: number;
}

export interface LogicGene {
  name: string;
  role: string;
  state: "ON" | "OFF";
  direction: "up" | "down";
}

export interface LogicGraph {
  genes: LogicGene[];
  mid_gate: "AND" | "OR";
  outer_gate: "AND" | "OR";
  invert: boolean;
  output: string;
  caption: string;
}

export interface CandidateDesign {
  switch_sequence: string;
  structure: string;
  toehold_length: number;
  sequence_length_bp: number;
  plasmid_segments: PlasmidSegment[];
  logic_graph: LogicGraph;
}

export interface Candidate {
  id: string;
  run_id: string;
  /** What this candidate expresses. Runs may target several equivalent outputs. */
  output: string | null;
  engine_ref: string;
  rank: number | null;
  overall_score: number | null;
  gate_family: string;
  logic_type: string;
  summary: string;
  warnings: string[];
  is_rejected: boolean;
  rejection_reason: string;
}

export interface CandidateDetail extends Candidate {
  triggers: { features: Array<Record<string, unknown>> };
  design: CandidateDesign;
  metrics: Metric[];
}

export interface Artifact {
  id: string;
  run_id: string;
  candidate_id: string | null;
  kind: string;
  media_type: string;
  checksum_sha256: string;
  size_bytes: number;
  download_url: string;
  created_at: string;
}

export interface Annotation {
  id: string;
  candidate_id: string;
  author: string;
  text: string;
  decision_tag: DecisionTag;
  created_at: string;
}

export interface Paginated<T> {
  items: T[];
  count: number;
}

/** The wizard's configuration, frozen into params_snapshot at submission. */
export interface RunParams {
  schema_version?: string;
  organism?: string;
  input_mode?: InputMode;
  logic?: { set_a: string[]; set_b: string[]; expression: string };
  mechanism?: string;
  /** All outputs are equivalent; each selected one gets its own plasmid candidates. */
  payload?: { outputs: string[]; custom_sequence: string | null };
  constraints?: {
    max_leakage: number;
    min_mfe: number;
    min_off_target_score: number;
    max_length_bp: number;
    target_gc: number;
  };
  mock?: { candidate_count?: number; step_delay?: number; fail?: boolean };
  [key: string]: unknown;
}
