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

/** A selectable plasmid backbone vector, as advertised by the engine
 * (docs/plasmids.md Q13). */
export interface Backbone {
  key: string;
  name: string;
  length_bp: number;
}

export interface Version {
  app_version: string;
  api_schema_version: string;
  engine: string;
  engine_version: string;
  engine_schema_version: string;
  gate_families: GateFamily[];
  scoring_profiles: string[];
  available_backbones: Backbone[];
}

export interface ExampleDataset {
  key: string;
  label: string;
  description: string;
}

/** docs/public-datasets.md — a curated organism -> experiment -> comparison catalog,
 * generalizing ExampleDataset from one bundled key to many, sourced from real public
 * transcriptomics providers. Named OrganismInfo, not Organism — compile/Steps.tsx
 * already exports Organism as the wizard's own "ecoli" | "yeast" | "human" union, and
 * the wizard scopes public-dataset browsing to its own organism picker rather than
 * fetching this list (avoids a design organism disagreeing with a data organism). */
export interface OrganismInfo {
  key: string;
  name: string;
}

export interface PublicExperiment {
  experiment_key: string;
  organism: string;
  provider: string;
  accession: string;
  title: string;
  source_url: string;
}

export interface PublicComparison {
  comparison_key: string;
  comparison_id: string;
  label: string;
  experimental_condition: string;
  reference_condition: string;
  gene_count: number;
}

/** The info card (compile UI §12) shown before a researcher commits to loading it. */
export interface PublicDatasetInfo {
  comparison_key: string;
  provider: string;
  organism: string;
  experiment_accession: string;
  experiment_title: string;
  comparison_id: string;
  comparison_label: string;
  experimental_condition: string;
  reference_condition: string;
  source_url: string;
  retrieved_at: string;
  gene_count: number;
  genes_with_p_value: number;
  genes_with_adjusted_p_value: number;
  analysis_method: string;
  publication_doi: string;
}

export interface DatasetProvenance {
  provider: string;
  organism: string;
  experiment_accession: string;
  experiment_title: string;
  comparison_id: string;
  comparison_label: string;
  experimental_condition: string;
  reference_condition: string;
  source_url: string;
  retrieved_at: string;
  analysis_method: string;
  publication_doi: string;
}

export interface DatasetPreviewRow {
  gene_id: string;
  gene_symbol: string | null;
  log2fc: number | null;
  pvalue: number | null;
  padj: number | null;
}

/** Ranked by |log2FC| descending and capped server-side — see
 * apps.datasets.services.preview_expression_rows. */
export interface DatasetPreview {
  rows: DatasetPreviewRow[];
  total_rows: number;
  truncated: boolean;
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
  name: string;
  filename: string;
  checksum_sha256: string;
  size_bytes: number;
  schema_version: string;
  validation_status: ValidationStatus;
  validation_report: ValidationReport;
  /** Only present for a dataset materialized from the public catalog — null for a
   * plain upload, which has no provider to cite. */
  provenance: DatasetProvenance | null;
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
  dataset_id: string | null;
  status: RunStatus;
  stage: string;
  progress_pct: number;
  input_mode: InputMode;
  trigger_sequence: string;
  organism: string;
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

/** Categories the download UI groups artifacts under (apps.results.models.ArtifactCategory). */
export type ArtifactCategory =
  | "summary"
  | "sequences"
  | "plasmids"
  | "diagrams"
  | "reports"
  | "other";

export interface Artifact {
  id: string;
  run_id: string;
  candidate_id: string | null;
  kind: string;
  /** The server's grouping for this artifact — never re-derived from `kind` client-side. */
  category: ArtifactCategory;
  /** A human-readable description of what this file is, e.g. "Switch sequence (FASTA)". */
  label: string;
  /** The original filename, e.g. "cand-006.fasta". */
  name: string;
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

/** ADR 0006. Never carries the secret except right after creation/regeneration. */
export interface ApiKey {
  id: string;
  label: string;
  prefix: string;
  scopes: string[];
  max_concurrent_runs: number;
  rate_per_minute: number;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

/** The one shape that carries a secret — shown once, on POST /auth/keys and
 * POST /auth/keys/{id}/regenerate. Never persist this past the page that shows it. */
export interface ApiKeyCreated extends ApiKey {
  secret: string;
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
  /**
   * A per-run override of the scoring profile's hard filters (engine.scoring.profiles
   * X7) — the same shape POST /api/design validates. Metric names must be ones the
   * engine's DEFAULT_V1 profile actually knows (GET /api/version.metrics); an
   * unrecognised name is rejected at submission, not silently discarded.
   */
  scoring?: {
    /** `reason` is required by the API (api/params.py) — it becomes the rejected
     * candidate's recorded rejection_reason. */
    hard_filters?: { metric: string; minimum?: number; maximum?: number; reason: string }[];
  };
  /**
   * The plasmid vector the circuit gets assembled onto (docs/plasmids.md Q13). Exactly
   * one of the two fields, or neither (today's bare four-segment construct, unchanged) —
   * the API rejects both being set at once.
   */
  backbone?: { catalog_key?: string; custom_genbank?: string };
  /**
   * Informational only (compile/Steps.tsx's "Specific Gene" route) — recorded on the
   * submission so the run documents which gene the researcher had in mind, but not
   * resolved to a sequence or wired into the pipeline. Rides through as a free-form
   * params key; the engine does not read it today.
   */
  target_gene?: { organism: string; gene_id: string; gene_symbol: string | null };
  mock?: { candidate_count?: number; step_delay?: number; fail?: boolean };
  [key: string]: unknown;
}
