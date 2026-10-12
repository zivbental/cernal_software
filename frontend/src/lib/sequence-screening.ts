import { screeningSchema, type SequenceScreening } from "@/api/screening";

export type ScreeningState = SequenceScreening["status"] | "stale" | "checking";
export interface ScreeningView {
  state: ScreeningState;
  label: string;
  reason: string;
  evidence?: SequenceScreening;
}

export const screeningLabels: Record<ScreeningState, string> = {
  not_screened: "Not screened",
  unavailable: "Screening unavailable",
  checking: "Verifying screening identity",
  pending: "Screening pending",
  error: "Screening failed",
  flagged: "Flagged for review",
  clear: "No concerns detected by this screening",
  stale: "Screening result is stale or mismatched",
};
export function screeningView(state: ScreeningState, reason: string, evidence?: SequenceScreening): ScreeningView {
  return { state, label: screeningLabels[state], reason, evidence };
}

/** Identity check only. This does not screen sequences or infer an engine verdict. */
export async function assessScreening(
  raw: unknown,
  subject: { runId: string; candidateId: string; sequence: string },
  now = Date.now(),
): Promise<ScreeningView> {
  if (raw == null) return screeningView("not_screened", "No screening evidence was supplied for this candidate.");
  const parsed = screeningSchema.safeParse(raw);
  if (!parsed.success) return screeningView("unavailable", "The screening response is incomplete or unsupported.");
  const report = parsed.data;
  const identity = report.subject;
  if (identity.run_id !== subject.runId || identity.candidate_id !== subject.candidateId) {
    return screeningView("stale", "The result belongs to a different run or candidate.");
  }
  // Preserve U; do not silently convert DNA to RNA, strip whitespace or reinterpret FASTA.
  const sequence = typeof subject.sequence === "string" ? subject.sequence.toUpperCase() : "";
  if (!/^[ACGU]+$/.test(sequence)) return screeningView("unavailable", "The saved switch sequence cannot be verified using this contract.");
  let hash: string;
  try {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(sequence));
    hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
  } catch {
    return screeningView("unavailable", "Sequence identity verification is unavailable in this browser.");
  }
  if (hash !== identity.sha256 || sequence.length !== identity.length) {
    return screeningView("stale", "The screened sequence does not match the saved switch sequence.");
  }
  const completed = report.status === "clear" || report.status === "flagged";
  if (completed && (!report.screened_at || !report.valid_until || !report.provenance)) {
    return screeningView("unavailable", "Completed screening evidence is missing time or provenance.");
  }
  if (report.screened_at && Date.parse(report.screened_at) > now) {
    return screeningView("stale", "The screening timestamp is in the future.");
  }
  if (report.valid_until && (Date.parse(report.valid_until) <= now ||
      (report.screened_at && Date.parse(report.valid_until) <= Date.parse(report.screened_at)))) {
    return screeningView("stale", "The backend validity window has expired or is inconsistent.");
  }
  if (report.status === "clear" && report.findings.length) {
    return screeningView("unavailable", "The screening status conflicts with its findings.");
  }
  const reasons: Record<SequenceScreening["status"], string> = {
    not_screened: "Screening has not been performed for this sequence.",
    unavailable: "The backend could not provide screening evidence.",
    pending: "The backend has not finished screening this sequence.",
    error: "The screening attempt failed. No completed result is available.",
    flagged: "This screening requires review by the responsible team.",
    clear: "This result applies only to the identified switch sequence and recorded screening scope.",
  };
  return screeningView(report.status, reasons[report.status], report);
}
