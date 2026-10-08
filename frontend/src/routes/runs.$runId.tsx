import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AlertTriangle, Ban, CircuitBoard, Dna, Loader2, FileText } from "lucide-react";

import { api } from "@/api/client";
import { useCancelRun, useCandidate, useCandidates, useRun, useRunStatus } from "@/api/queries";
import type { Candidate, RunStatusResponse } from "@/api/types";
import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Panel, SectionHeading } from "@/components/layout/Primitives";
import { CandidateReview } from "@/components/results/CandidateReview";
import { ArtifactDownloads } from "@/components/results/ArtifactDownloads";
import { MetricGrid } from "@/components/results/MetricGrid";
import { PlasmidLegend, PlasmidRing } from "@/components/results/PlasmidRing";
import { LogicCircuitView } from "@/components/results/LogicCircuit";
import { RunStatusBadge } from "@/components/results/RunStatusBadge";
import { PrecisionFilters, type Filters, DEFAULT_FILTERS } from "@/components/results/PrecisionFilters";
import { Loading } from "@/components/layout/Loading";

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
        title={done ? "Computational Design Results" : status.data.status === "FAILED" ? "Run failed" : status.data.status === "CANCELLED" ? "Run cancelled" : "Compiling your circuit"}
        description={
          done
            ? "Candidates ranked using provisional folding and accessibility models. Off-target specificity is unmeasured; computation completion does not authorize sequence release."
            : "The engine is working. This page updates by itself — you can leave and come back."
        }
        actions={<RunStatusBadge status={status.data.status} />}
      />

      <WarningList title="Run warnings" warnings={status.data.warnings ?? []} />
      {run.isError && <p role="alert">Could not load the frozen run configuration. <button onClick={() => run.refetch()}>Retry</button></p>}
      {run.data && <details className="mb-4 rounded-xl border border-border p-4"><summary>Run provenance and frozen configuration</summary><p>Engine {run.data.engine_version || "pending"} · Seed {run.data.seed ?? "unspecified"} · Host {run.data.organism}</p><pre className="mt-2 overflow-auto text-xs">{JSON.stringify(run.data.params_snapshot, null, 2)}</pre></details>}
      {done ? <Results runId={runId} outputs={run.data?.params_snapshot.payload?.outputs ?? []} /> : <RunProgress runId={runId} status={status.data} />}
    </>
  );
}

/* ---------- progress, failure, cancellation ---------- */

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

function Results({ runId, outputs: configuredOutputs }: { runId: string; outputs: string[] }) {
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<"plasmid" | "logic">("plasmid");

  const [outputFilter, setOutputFilter] = useState<string | null>(null);
  const candidates = useCandidates(runId, {
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
      <Panel className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 grid-clinical opacity-60" />
        <div className="relative">
          <SectionHeading
            kicker="Step 04 · Fulfillment"
            title="Ranked Candidates"
            desc={`${candidates.data?.count ?? 0} matching candidates. Showing ${items.length ? offset + 1 : 0}–${offset + items.length}. Filters apply to the entire run.`}
          />

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
                      {detail.data.engine_ref} ·{" "}
                      {view === "plasmid" ? "Plasmid Map" : "Logic Circuit"}
                    </div>
                    <div className="inline-flex rounded-lg border border-border bg-surface p-1">
                      {(
                        [
                          { k: "plasmid", label: "Plasmid Map", Icon: Dna },
                          { k: "logic", label: "Logic Circuit", Icon: CircuitBoard },
                        ] as const
                      ).map((tab) => (
                        <button
                          key={tab.k}
                          onClick={() => setView(tab.k)}
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

                  <WarningList title="Candidate warnings" warnings={detail.data.warnings ?? []} />
                  <p className="mt-3 text-xs">{detail.data.is_rejected ? "Rejected from ranking" : "Accepted for computational ranking"}. {detail.data.design.plasmid_segments?.some((segment) => segment.kind === "backbone") ? "Vector-containing construct" : "Bare expression cassette"}. Export release is a separate decision; see warnings and available artifacts.</p>
                  <details className="mt-3"><summary>Reference identity and model provenance</summary><pre className="overflow-auto text-xs">{JSON.stringify({ triggers: detail.data.triggers, design: detail.data.design }, null, 2)}</pre></details>
                  <div className="mt-6 rounded-xl border border-border bg-card p-4">
                    <div className="mb-3 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                      Score decomposition
                    </div>
                    <MetricGrid metrics={detail.data.metrics} />
                  </div>

                  <CandidateReview key={detail.data.id} candidateId={detail.data.id} />
                  <div className="mt-4 rounded-xl border border-border bg-card p-3">
                    <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                      Switch sequence 5&rsquo; → 3&rsquo;
                    </div>
                    <div className="mt-1 break-all font-mono text-[11px] text-foreground">
                      {detail.data.design.switch_sequence}
                    </div>
                  </div>
                </>
              ) : selectedId ? <Loading /> : <p>No candidate is selected. This run has no results matching the current filters.</p>}
            </div>

            <div>
              <PrecisionFilters filters={filters} onChange={(next) => { setFilters(next); setOffset(0); }} />

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
      <ArtifactDownloads runId={runId} />
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
            {candidate.rank ? `#${candidate.rank}` : "—"}
          </span>
          <span className="truncate font-mono text-xs text-muted-foreground">
            {candidate.engine_ref}
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
        <div className="mt-0.5 truncate text-xs text-muted-foreground">{candidate.summary}</div>
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
        <div className="font-mono text-[10px] text-muted-foreground">score</div>
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

function WarningList({ title, warnings }: { title: string; warnings: string[] }) {
  const [offset, setOffset] = useState(0);
  if (!warnings.length) return null;
  const start = Math.min(offset, Math.floor((warnings.length - 1) / 50) * 50);
  return <details className="my-4 rounded-xl border border-amber-500/40 bg-amber-500/5 p-4"><summary>{title} ({warnings.length})</summary><ul className="mt-2 space-y-1 text-sm">{warnings.slice(start, start + 50).map((warning, index) => <li key={start + index}>{warning}</li>)}</ul>{warnings.length > 50 && <nav aria-label={`${title} pages`} className="mt-2 flex justify-between"><button disabled={start === 0} onClick={() => setOffset(Math.max(0, start - 50))}>Previous warnings</button><span>{start + 1}–{Math.min(start + 50, warnings.length)} of {warnings.length}</span><button disabled={start + 50 >= warnings.length} onClick={() => setOffset(start + 50)}>Next warnings</button></nav>}</details>;
}
