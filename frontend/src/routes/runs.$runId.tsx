import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AlertTriangle, Ban, CircuitBoard, ChevronDown, Dna, Loader2, FileText } from "lucide-react";

import { api } from "@/api/client";
import { useCancelRun, useCandidate, useCandidates, useRenameRun, useRun, useRunStatus } from "@/api/queries";
import type { Candidate, Run, RunStatusResponse } from "@/api/types";
import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Panel, SectionHeading } from "@/components/layout/Primitives";
import { CandidateReview } from "@/components/results/CandidateReview";
import { ArtifactDownloads } from "@/components/results/ArtifactDownloads";
import { MetricGrid } from "@/components/results/MetricGrid";
import { AndGateEvidence } from "@/components/results/AndGateEvidence";
import { PlasmidLegend, PlasmidRing } from "@/components/results/PlasmidRing";
import { LogicCircuitView } from "@/components/results/LogicCircuit";
import { RnaStructureView } from "@/components/results/RnaStructureView";
import { RunStatusBadge } from "@/components/results/RunStatusBadge";
import { SequenceScreening } from "@/components/results/SequenceScreening";
import { PrecisionFilters, type Filters, DEFAULT_FILTERS } from "@/components/results/PrecisionFilters";
import { Loading } from "@/components/layout/Loading";
import { Checkbox } from "@/components/ui/checkbox";

export const Route = createFileRoute("/runs/$runId")({
  component: () => (
    <RequireAuth>
      <AppShell>
        <RunPage />
      </AppShell>
    </RequireAuth>
  ),
});

function RunPage() {
  const { runId } = Route.useParams();
  const status = useRunStatus(runId);
  const run = useRun(runId);

  if (status.isLoading) return <Loading />;
  if (status.isError) return <p role="alert">Could not refresh run status. <button onClick={() => status.refetch()}>Retry</button></p>;
  if (!status.data) {
    return <p className="text-sm text-muted-foreground">That run could not be found.</p>;
  }

  const done = status.data.status === "COMPLETED";

  return (
    <>
      <PageHeader
        kicker={
          <>
            <CircuitBoard className="h-3 w-3" />
            <Link to="/dashboard" className="hover:text-foreground">
              Run
            </Link>
            <span>/</span>
            <span className="font-mono normal-case tracking-normal">{runId.slice(0, 8)}</span>
          </>
        }
        title={run.data?.name || status.data.name || (done ? "Computational Design Results" : status.data.status === "FAILED" ? "Run failed" : status.data.status === "CANCELLED" ? "Run cancelled" : "Compiling your circuit")}
        description={
          done
            ? "Compare design candidates and download the run summary and available files. Sequence files appear only after release review."
            : "The engine is working. This page updates by itself — you can leave and come back."
        }
        actions={<RunStatusBadge status={status.data.status} />}
      />

      {run.data && <RunNameEditor key={runId} runId={runId} name={run.data.name || ""} />}
      {run.isError && <p role="alert">Could not load the frozen run configuration. <button onClick={() => run.refetch()}>Retry</button></p>}
      {run.data && <RunSettingsSummary run={run.data} />}
      {done ? (
        run.data ? <Results key={runId} topN={run.data.params_snapshot.top_n} runId={runId} outputs={run.data.params_snapshot.payload?.outputs ?? []} /> : run.isLoading ? <Loading /> : null
      ) : <RunProgress runId={runId} status={status.data} />}
    </>
  );
}

/* ---------- progress, failure, cancellation ---------- */

function RunNameEditor({ runId, name }: { runId: string; name: string }) {
  const rename = useRenameRun(runId);
  const [draft, setDraft] = useState(name);
  return (
    <form className="mb-4 flex flex-wrap items-end gap-2" onSubmit={async (event) => {
      event.preventDefault();
      try { const saved = await rename.mutateAsync(draft); setDraft(saved.name); } catch { /* Keep draft for retry. */ }
    }}>
      <div className="min-w-0 flex-1 basis-64">
        <label htmlFor="edit-run-name" className="block text-xs font-medium">Run name</label>
        <input id="edit-run-name" value={draft} onChange={(event) => { setDraft(event.target.value); rename.reset(); }}
          maxLength={120} disabled={rename.isPending} aria-describedby="edit-run-name-help"
          className="mt-1 w-full rounded-lg border border-border bg-card px-3 py-2 text-sm" />
      </div>
      <button type="submit" disabled={rename.isPending || draft === name}
        className="rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-50">{rename.isPending ? "Saving…" : "Save name"}</button>
      <p id="edit-run-name-help" className="basis-full text-xs text-muted-foreground">Up to 120 characters. Leave blank to use the run ID. Renaming does not change the configuration.</p>
      {rename.isError && <p role="alert" className="basis-full text-sm text-destructive">{rename.error.message}</p>}
      {rename.isSuccess && <p role="status" className="basis-full text-sm">Run name saved.</p>}
    </form>
  );
}

const SETTING_EXPLANATIONS: Record<string, string> = {
  "Organism": "The cell type the design was prepared for.",
  "Input": "Whether the run used a transcript sequence, a gene reference, or expression data.",
  "Switch design": "The RNA switch design family used for this run.",
  "Outputs": "The output protein or effect selected for the design.",
  "Plasmid backbone": "The vector chosen to carry the expression cassette. A custom vector is represented by its label here; its sequence is not shown.",
  "Insertion point": "The boundary in the selected custom vector where the expression cassette was placed.",
  "Codon optimization": "Whether the selected output sequence was requested to be adapted to the chosen organism.",
  "Maximum gates": "The maximum number of logic gates permitted in one proposed circuit.",
  "Results shown": "The number of top-ranked accepted candidates selected for the initial view.",
  "Scoring profile": "The scoring configuration used to order candidates. A score is a ranking aid, not a probability.",
};

const OUTPUT_LABELS: Record<string, string> = {
  gfp: "GFP",
  mcherry: "mCherry",
  luciferase: "Luciferase",
  ampr: "AmpR",
  apoptosis: "Apoptosis",
  other: "Custom",
};

function RunSettingsSummary({ run }: { run: Run }) {
  const [explain, setExplain] = useState(false);
  const params = run.params_snapshot;
  const organismName: Record<string, string> = {
    ecoli: "E. coli", yeast: "Yeast", human: "Human", c_acnes: "C. acnes",
  };
  const mechanismName = params.mechanism?.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  const rows: Array<[string, string]> = [
    ["Organism", organismName[run.organism] ?? run.organism],
    ["Input", run.input_mode === "de" ? "Expression data" : run.input_mode === "gene" ? "Reference gene" : "Transcript sequence"],
    ...(mechanismName ? [["Switch design", mechanismName] as [string, string]] : []),
    ...(params.payload?.outputs?.length ? [["Outputs", params.payload.outputs.map((output) => OUTPUT_LABELS[output] ?? output).join(", ")] as [string, string]] : []),
    ["Plasmid backbone", params.backbone?.catalog_key ? (params.backbone.catalog_key === "psb1c3" ? "pSB1C3" : params.backbone.catalog_key) : params.backbone?.custom_genbank ? "Custom vector" : "No backbone"],
    ...(params.backbone?.insertion_index !== undefined ? [["Insertion point", `0-based boundary ${params.backbone.insertion_index}`] as [string, string]] : []),
    ["Codon optimization", params.payload?.optimize_codons ? "On" : "Off"],
    ...(params.constraints?.max_circuit_gates !== undefined ? [["Maximum gates", String(params.constraints.max_circuit_gates)] as [string, string]] : []),
    ...(params.top_n !== undefined ? [["Results shown", String(params.top_n)] as [string, string]] : []),
    ["Scoring profile", run.scoring_profile],
  ];

  return (
    <details className="mb-5 overflow-hidden rounded-xl border border-border bg-surface group">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint [&::-webkit-details-marker]:hidden">
        <div className="min-w-0 flex-1">
          <span className="block text-xs font-medium text-mint">Optional details</span>
          <span className="block text-sm font-semibold text-foreground">Show plasmid settings and run details</span>
        </div>
        <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-border px-4 py-4">
        <div className="flex items-start gap-2">
          <Checkbox id="explain-run-settings" checked={explain} onCheckedChange={(checked) => setExplain(checked === true)} />
          <label htmlFor="explain-run-settings" className="cursor-pointer text-sm text-foreground">Explain each setting</label>
        </div>
        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label} className="rounded-lg border border-border bg-card p-3">
              <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
              <dd className="mt-1 text-sm text-foreground">{value}</dd>
              {explain && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{SETTING_EXPLANATIONS[label]}</p>}
            </div>
          ))}
        </dl>
        <p className="mt-4 text-xs text-muted-foreground">Engine {run.engine_version || "pending"} · Seed {run.seed ?? "unspecified"}</p>
      </div>
    </details>
  );
}

function RunProgress({ runId, status }: { runId: string; status: RunStatusResponse }) {
  const cancel = useCancelRun(runId);

  if (status.status === "FAILED") {
    return (
      <Panel>
        <div className="flex items-start gap-4">
          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-destructive/10">
            <AlertTriangle className="h-5 w-5 text-destructive" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">This run did not finish</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {status.error_summary ?? "The analysis failed."}
            </p>
            <p className="mt-3 text-sm text-muted-foreground">
              Your dataset and configuration are unchanged — fix the input and compile
              again.
            </p>
          </div>
        </div>
      </Panel>
    );
  }

  if (status.status === "CANCELLED") {
    return (
      <Panel>
        <div className="flex items-start gap-4">
          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-secondary">
            <Ban className="h-5 w-5 text-muted-foreground" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">Run cancelled</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              The engine stopped at a safe point. Your submitted configuration and logs remain available; partial results depend on where cancellation occurred.
            </p>
          </div>
        </div>
      </Panel>
    );
  }

  return (
    <Panel>
      <div className="flex items-center justify-between gap-6">
        <div>
          <div className="font-mono text-[11px] uppercase tracking-wider text-mint">
            {status.status === "QUEUED" ? "Waiting for a worker" : "In progress"}
          </div>
          <h2 className="mt-1 text-lg font-semibold text-foreground">
            {status.stage || "Queued"}
          </h2>
        </div>
        <div className="font-mono text-3xl font-semibold text-foreground">
          {status.progress_pct}%
        </div>
      </div>

      <div className="mt-5 h-2 w-full overflow-hidden rounded-full bg-border">
        <div
          className="h-2 rounded-full bg-gradient-mint transition-all duration-700"
          style={{ width: `${Math.max(status.progress_pct, 2)}%` }}
        />
      </div>

      {status.status === "QUEUED" && status.worker_available === false && (
        <p className="mt-4 text-sm text-destructive" role="status">
          The analysis worker is offline. Your submission is saved and will start when
          the worker reconnects. If this persists, contact the team.
        </p>
      )}

      <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Updating every few seconds
        </div>
        <button
          onClick={() => cancel.mutate()}
          disabled={cancel.isPending || Boolean(cancel.data)}
          className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-foreground hover:border-destructive/40 hover:text-destructive disabled:opacity-60"
        >
          <Ban className="h-3.5 w-3.5" />
          {cancel.data ? "Cancellation requested" : "Cancel run"}
        </button>
      </div>

      {cancel.isError && <p role="alert">Cancellation failed. Please retry.</p>}
      {cancel.data && (
        <p className="mt-3 text-xs text-muted-foreground">
          Cancellation is cooperative — the engine stops at the next stage boundary rather
          than being killed mid-calculation.
        </p>
      )}
    </Panel>
  );
}

/* ---------- results ---------- */

function Results({ runId, outputs: configuredOutputs, topN: savedTopN }: { runId: string; outputs: string[]; topN?: number }) {
  // Older /runs submissions allowed freeform params; invalid historical values mean all results.
  const topN = typeof savedTopN === "number" && Number.isInteger(savedTopN) && savedTopN >= 1 && savedTopN <= 1000 ? savedTopN : undefined;
  const [showAll, setShowAll] = useState(false);
  const limited = !showAll && topN !== undefined;
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<"plasmid" | "logic" | "rna">("plasmid");

  const [outputFilter, setOutputFilter] = useState<string | null>(null);
  const candidates = useCandidates(runId, {
    topN: limited ? topN : undefined,
    includeRejected: filters.includeRejected,
    sort: filters.sort,
    limit: 50,
    offset,
    output: outputFilter ?? undefined,
    minScore: filters.minScore / 100,
  });

  const items = candidates.data?.items ?? [];
  // A run can target several equivalent outputs, each compiled into its own plasmids.
  const outputs = [...new Set([...configuredOutputs.map((output) => ({ gfp: "GFP", other: "Custom", mcherry: "mCherry", luciferase: "Luciferase", ampr: "AmpR", apoptosis: "Apoptosis" }[output] ?? output)), ...items.map(outputOf).filter(Boolean)])] as string[];
  const visible = items;

  useEffect(() => {
    if (!visible.some((candidate) => candidate.id === selectedId)) setSelectedId(visible[0]?.id ?? null);
  }, [selectedId, visible]);

  const detail = useCandidate(selectedId);

  if (candidates.isLoading) return <Loading />;
  if (candidates.isError) return <p role="alert">Could not load candidates. <button onClick={() => candidates.refetch()}>Retry</button></p>;

  return (
    <div className="space-y-6">
      <ArtifactDownloads runId={runId} />
      <Panel className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 grid-clinical opacity-60" />
        <div className="relative">
          <SectionHeading
            kicker="Step 04 · Fulfillment"
            title="Ranked Candidates"
            desc={`${candidates.data?.count ?? 0} matching candidates. Showing ${items.length ? offset + 1 : 0}–${offset + items.length}. ${limited ? `Filters apply within the globally top ${topN} accepted results.` : "Filters apply to the entire run."}`}
          />

          <div className="mb-4 space-y-2 text-sm">
            <label className="flex items-center gap-2">
              Result view
              <select aria-label="Result view" value={limited ? "top" : "all"}
                onChange={(event) => {
                  setShowAll(event.target.value === "all");
                  setFilters((current) => ({ ...current, includeRejected: false }));
                  setOffset(0);
                }} className="rounded-md border border-border bg-card px-3 py-2">
                {topN !== undefined && <option value="top">Top {topN} accepted results</option>}
                <option value="all">All stored results</option>
              </select>
            </label>
            <p className="text-xs text-muted-foreground">
              The display limit selects the globally top-ranked accepted results before filters or table sorting. It does not reduce computation or stored results.
              Exports retain all results. Showing rejected candidates switches to all stored results.
            </p>
          </div>

          {outputs.length > 1 && (
            <div className="mb-6 flex flex-wrap items-center gap-2">
              <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                Output
              </span>
              {[null, ...outputs].map((output) => (
                <button
                  key={output ?? "all"}
                  onClick={() => { setOutputFilter(output); setOffset(0); }}
                  className={`rounded-md border px-3 py-1 text-xs transition ${
                    outputFilter === output
                      ? "border-mint bg-mint/10 text-mint"
                      : "border-border bg-surface text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {output ?? "All outputs"}

                </button>
              ))}
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-[1.15fr_1fr]">
            <div className="rounded-2xl border border-border bg-gradient-to-br from-surface to-card p-6">
              {detail.isError ? <p role="alert">Could not load candidate detail. <button onClick={() => detail.refetch()}>Retry</button></p> : detail.data ? (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                      {detail.data.rank ? `Candidate #${detail.data.rank}` : "Candidate details"} ·{" "}
                      {view === "plasmid" ? "Plasmid Map" : view === "logic" ? "Logic Circuit" : "RNA Structure"}
                    </div>
                    <div className="inline-flex flex-wrap rounded-lg border border-border bg-surface p-1">
                      {(
                        [
                          { k: "plasmid", label: "Plasmid Map", Icon: Dna },
                          { k: "logic", label: "Logic Circuit", Icon: CircuitBoard },
                          { k: "rna", label: "RNA Structure", Icon: Dna },
                        ] as const
                      ).map((tab) => (
                        <button
                          key={tab.k}
                          onClick={() => setView(tab.k)}
                          aria-pressed={view === tab.k}
                          className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-xs transition ${
                            view === tab.k
                              ? "bg-card font-medium text-foreground shadow-clinical"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          <tab.Icon className="h-3.5 w-3.5" />
                          {tab.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="mt-5 grid place-items-center">
                    {view === "plasmid" ? (
                      <div>
                        <PlasmidRing candidate={detail.data} />
                        <PlasmidLegend segments={detail.data.design.plasmid_segments ?? []} />
                      </div>
                    ) : view === "rna" ? (
                      <RnaStructureView key={detail.data.id} candidate={detail.data} />
                    ) : (
                      <div className="w-full">
                        <LogicCircuitView
                          logic={toDesignLogic(detail.data.design.logic_graph)}
                          activeGate="mid"
                        />
                        <p className="mt-4 text-center font-mono text-[11px] text-muted-foreground">
                          {detail.data.design.logic_graph?.caption}
                        </p>
                      </div>
                    )}
                  </div>

                  <SequenceScreening key={detail.data.id} candidate={detail.data} />
                  <p className="mt-3 text-xs text-muted-foreground">{detail.data.is_rejected ? "Not included in the ranked results." : "Included in the computational ranking."} {detail.data.design.plasmid_segments?.some((segment) => segment.kind === "backbone") ? "Includes a selected vector." : "Shown as an expression cassette without a vector."} Sequence downloads are available only after release review.</p>
                  <details className="mt-3 rounded-lg border border-border bg-card p-3">
                    <summary className="cursor-pointer text-sm font-medium">Show technical design labels</summary>
                    <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                      <div><dt className="text-muted-foreground">Candidate reference</dt><dd className="mt-0.5 font-mono">{detail.data.engine_ref}</dd></div>
                      <div><dt className="text-muted-foreground">Switch family</dt><dd className="mt-0.5">{detail.data.gate_family.replaceAll("_", " ")}</dd></div>
                      <div><dt className="text-muted-foreground">Logic type</dt><dd className="mt-0.5">{detail.data.logic_type.replaceAll("_", " ")}</dd></div>
                      {detail.data.output && <div><dt className="text-muted-foreground">Selected output</dt><dd className="mt-0.5">{detail.data.output}</dd></div>}
                    </dl>
                  </details>
                  {detail.data.design.and_gate && <AndGateEvidence info={detail.data.design.and_gate} />}
                  <details className="mt-4 rounded-xl border border-border bg-card p-4">
                    <summary className="cursor-pointer text-sm font-medium text-foreground">Why this candidate ranks this way</summary>
                    <p className="mt-2 text-xs text-muted-foreground">The breakdown below explains how the computational ranking was calculated. It does not estimate experimental success.</p>
                    <div className="mt-4"><MetricGrid metrics={detail.data.metrics} /></div>
                  </details>

                  <CandidateReview key={detail.data.id} candidateId={detail.data.id} />
                  <div className="mt-4 rounded-xl border border-border bg-card p-3">
                    <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                      Switch sequence 5&rsquo; → 3&rsquo;
                    </div>
                    <div className="mt-1 break-all font-mono text-[11px] text-foreground">
                      {detail.data.design.sequence_release?.release_allowed === true
                        ? detail.data.design.switch_sequence
                        : "Sequence withheld pending release approval. Scores and computational eligibility do not authorize sequence release."}
                    </div>
                  </div>
                </>
              ) : selectedId ? <Loading /> : <p>No candidate is selected. This run has no results matching the current filters.</p>}
            </div>

            <div>
              <PrecisionFilters filters={filters} onChange={(next) => { setFilters(next); if (next.includeRejected) setShowAll(true); setOffset(0); }} />

              <div className="mt-4 space-y-2">
                {visible.map((candidate) => (
                  <CandidateRow
                    key={candidate.id}
                    candidate={candidate}
                    output={outputs.length > 1 ? outputOf(candidate) : null}
                    selected={candidate.id === selectedId}
                    onSelect={() => setSelectedId(candidate.id)}
                  />
                ))}
                {visible.length === 0 && (
                  <div className="rounded-xl border border-dashed border-border bg-surface p-8 text-center text-sm text-muted-foreground">
                    No candidates match these filters. Loosen them to see more.
                  </div>
                )}
              </div>
            </div>
          </div>

          <nav aria-label="Candidate pages" className="mt-4 flex justify-between gap-4">
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button>
            <span>Page {Math.floor(offset / 50) + 1} of {Math.max(1, Math.ceil((candidates.data?.count ?? 0) / 50))}</span>
            <button disabled={offset + 50 >= (candidates.data?.count ?? 0)} onClick={() => setOffset(offset + 50)}>Next</button>
            <button disabled={offset + 50 >= (candidates.data?.count ?? 0)} onClick={() => setOffset(Math.floor(((candidates.data?.count ?? 1) - 1) / 50) * 50)}>Last</button>
          </nav>
          <div className="mt-8 border-t border-border pt-6">
            <button
              disabled
              title="Ordering requires a funded partner integration and explicit authorization"
              className="group inline-flex w-full cursor-not-allowed items-center justify-center gap-3 rounded-xl bg-gradient-deep px-6 py-4 text-sm font-semibold text-primary-foreground opacity-50"
            >
              <FileText className="h-4 w-4" />
              Synthesis ordering is planned and unavailable
            </button>
          </div>
        </div>
      </Panel>

      <a className="inline-block text-sm underline" href={api.url(`/runs/${runId}/review.json`)}>Export researcher notes and decisions (JSON)</a>
    </div>
  );
}

function CandidateRow({
  candidate,
  output,
  selected,
  onSelect,
}: {
  candidate: Candidate;
  output: string | null;
  selected: boolean;
  onSelect: () => void;
}) {
  const score = candidate.overall_score;
  return (
    <button
      onClick={onSelect}
      className={`flex w-full items-center gap-4 rounded-xl border p-4 text-left transition ${
        selected ? "border-mint bg-mint/5 shadow-mint" : "border-border bg-surface hover:border-mint/40"
      }`}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-semibold text-foreground">
            {candidate.rank ? `Candidate #${candidate.rank}` : "Unranked candidate"}
          </span>
          {output && (
            <span className="shrink-0 rounded-md bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {output}
            </span>
          )}
          {candidate.is_rejected && (
            <span
              title={candidate.rejection_reason}
              className="rounded-md bg-destructive/10 px-1.5 py-0.5 font-mono text-[10px] text-destructive"
            >
              rejected
            </span>
          )}
        </div>
        <div className="mt-0.5 truncate text-xs text-muted-foreground">
          {candidate.output ? `Output: ${OUTPUT_LABELS[candidate.output] ?? candidate.output}` : "RNA switch design"}
        </div>
        {candidate.is_rejected && (
          <div className="mt-1 text-[11px] text-destructive">{candidate.rejection_reason}</div>
        )}
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-border">
          <div
            className="h-1 rounded-full bg-gradient-mint"
            style={{ width: `${Math.round((score ?? 0) * 100)}%` }}
          />
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className="font-mono text-lg font-semibold text-foreground">
          {score === null ? "—" : `${Math.round(score * 100)}%`}
        </div>
        <div className="font-mono text-[10px] text-muted-foreground">ranking</div>
      </div>
    </button>
  );
}

/** Bridge the engine's logic_graph onto the shape the design component draws. */
function toDesignLogic(graph: import("@/api/types").LogicGraph | undefined) {
  const genes = graph?.genes ?? [];
  return {
    genes: genes.map((g) => ({
      name: g.name,
      role: g.role,
      state: g.state,
      dir: g.direction,
    })),
    midGate: graph?.mid_gate ?? "AND",
    outerGate: graph?.outer_gate ?? "AND",
    invert: graph?.invert ?? false,
    output: graph?.output ?? "GFP",
    caption: graph?.caption ?? "",
  };
}

/** What a candidate expresses. Resolved by the API from design.logic_graph.output. */
const outputOf = (candidate: Candidate) => candidate.output;
