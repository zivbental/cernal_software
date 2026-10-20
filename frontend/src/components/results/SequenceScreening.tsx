import { useEffect, useId, useState } from "react";
import type { CandidateDetail } from "@/api/types";
import { assessScreening, screeningView, type ScreeningView } from "@/lib/sequence-screening";

const findingLabels = {
  review_required: "Review required",
  restricted_match: "Screening match requires review",
  incomplete_coverage: "Screening coverage is incomplete",
};

export function SequenceScreening({ candidate }: { candidate: CandidateDetail }) {
  const headingId = useId();
  const [checked, setChecked] = useState<{ candidate: CandidateDetail; view: ScreeningView }>();
  useEffect(() => {
    let active = true;
    let generation = 0;
    let completedGeneration = 0;
    const verify = () => {
      const current = ++generation;
      void assessScreening(candidate.sequence_screening, {
        runId: candidate.run_id, candidateId: candidate.id, sequence: candidate.design.switch_sequence,
      }).then(view => {
        if (active && current > completedGeneration) {
          completedGeneration = current;
          setChecked({ candidate, view });
        }
      });
    };
    verify();
    // Re-evaluate expiry even when the cached candidate response does not change.
    const timer = window.setInterval(verify, 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [candidate]);
  const view = checked?.candidate === candidate ? checked.view : screeningView("checking", "Checking the saved sequence against the reported identity.");
  const evidence = view.evidence;
  return (
    <section aria-labelledby={headingId} className="my-4 rounded-xl border border-border bg-card p-4">
      <h3 id={headingId} className="text-sm font-semibold">Sequence release status</h3>
      <p role="status" aria-live="polite" aria-atomic="true" className="mt-2 text-sm font-medium">{view.label}</p>
      <p className="mt-1 text-xs text-muted-foreground">{view.reason}</p>
      <p className="mt-2 text-xs">Switch sequence only. Full construct, payload, backbone and other sequences are not covered by this panel. Screening is not a safety guarantee or release authorization.</p>
      {evidence && <details className="mt-3 text-xs">
        <summary className="cursor-pointer rounded focus-visible:outline-2 focus-visible:outline-offset-2">Screening identity and provenance</summary>
        <dl className="mt-2 grid gap-1 break-all">
          <dt className="font-semibold">Subject</dt><dd>{evidence.subject.candidate_id} / {evidence.subject.run_id}</dd>
          <dt className="font-semibold">Scope</dt><dd>Saved switch sequence ({evidence.subject.length} nt; {evidence.subject.normalization})</dd>
          <dt className="font-semibold">Sequence SHA-256</dt><dd className="font-mono">{evidence.subject.sha256}</dd>
          <dt className="font-semibold">Screened at</dt><dd>{evidence.screened_at ?? "Not available"}</dd>
          <dt className="font-semibold">Valid until</dt><dd>{evidence.valid_until ?? "Not available"}</dd>
          <dt className="font-semibold">Tool / version</dt><dd>{evidence.provenance ? `${evidence.provenance.tool} / ${evidence.provenance.tool_version}` : "Not available"}</dd>
          <dt className="font-semibold">Database / version</dt><dd>{evidence.provenance ? `${evidence.provenance.database} / ${evidence.provenance.database_version}` : "Not available"}</dd>
          <dt className="font-semibold">Policy version</dt><dd>{evidence.provenance?.policy_version ?? "Not available"}</dd>
        </dl>
        {evidence.findings.length > 0 && <ul className="mt-2 list-disc pl-4">{[...new Set(evidence.findings)].map(finding => <li key={finding}>{findingLabels[finding]}</li>)}</ul>}
      </details>}
    </section>
  );
}
