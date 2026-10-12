import { z } from "zod";

/** Proposed optional API extension; see docs/sequence-screening.md. */
const text = z.string().trim().min(1).max(200);
export const screeningSchema = z.object({
  schema_version: z.literal(1),
  status: z.enum(["not_screened", "unavailable", "pending", "error", "flagged", "clear"]),
  subject: z.object({
    run_id: text,
    candidate_id: text,
    scope: z.literal("switch_sequence"),
    sha256: z.string().regex(/^[a-f0-9]{64}$/),
    length: z.number().int().positive(),
    normalization: z.literal("uppercase-rna-v1"),
  }),
  screened_at: z.string().datetime({ offset: true }).nullable(),
  valid_until: z.string().datetime({ offset: true }).nullable(),
  provenance: z.object({
    tool: text,
    tool_version: text,
    database: text,
    database_version: text,
    policy_version: text,
  }).nullable(),
  // Approved summaries only: never raw hits, matched sequences or coordinates.
  findings: z.array(z.enum(["review_required", "restricted_match", "incomplete_coverage"])).max(3),
});

export type SequenceScreening = z.infer<typeof screeningSchema>;
