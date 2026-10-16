// Synthetic identity-only fixtures. Never imported by application source.
import { createHash } from "node:crypto";
export const sequence = "ACGU";
export function report(status = "clear", overrides = {}) {
  return {
    schema_version: 1, status,
    subject: { run_id: "screening-run", candidate_id: "screening-candidate", scope: "switch_sequence",
      sha256: createHash("sha256").update(sequence).digest("hex"), length: sequence.length,
      normalization: "uppercase-rna-v1" },
    screened_at: "2026-01-01T00:00:00Z", valid_until: "2099-01-01T00:00:00Z",
    provenance: { tool: "Synthetic test tool", tool_version: "fixture-1", database: "Synthetic test database",
      database_version: "fixture-1", policy_version: "fixture-1" },
    findings: status === "flagged" ? ["review_required"] : [], ...overrides,
  };
}
