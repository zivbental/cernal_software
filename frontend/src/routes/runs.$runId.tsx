import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Ban,
  CircuitBoard,
  Download,
  Dna,
  Loader2,
  ShoppingCart,
} from "lucide-react";

import { api } from "@/api/client";
import {
  useArtifacts,
  useCancelRun,
  useCandidate,
  useCandidates,
  useRun,
  useRunStatus,
} from "@/api/queries";
import type { Candidate, RunStatusResponse } from "@/api/types";
import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Panel, SectionHeading } from "@/components/layout/Primitives";
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
            {run.data?.project_id ? (
              <Link
                to="/projects/$projectId"
                params={{ projectId: run.data.project_id }}
                className="hover:text-foreground"
              >
                Project
              </Link>
            ) : (
              "Run"
            )}
            <span>/</span>
            <span className="font-mono normal-case tracking-normal">{runId.slice(0, 8)}</span>
          </>
        }
        title={done ? "Optimized Plasmid Output" : "Compiling your circuit"}
        description={
          done
            ? "Candidates ranked across structural folding, leakage modelling and off-target screening."
            : "The engine is working. This page updates by itself — you can leave and come back."
        }
        actions={<RunStatusBadge status={status.data.status} />}
      />

      {done ? <Results runId={runId} /> : <RunProgress runId={runId} status={status.data} />}
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
              Your project, dataset and configuration are unchanged — fix the input and
              compile again.
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
              The engine stopped at the next safe point. Nothing was saved.
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

function Results({ runId }: { runId: string }) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<"plasmid" | "logic">("plasmid");

  const [outputFilter, setOutputFilter] = useState<string | null>(null);
  const candidates = useCandidates(runId, {
    includeRejected: filters.includeRejected,
    sort: filters.sort,
    limit: 200,
  });
  const artifacts = useArtifacts(runId);

  const items = candidates.data?.items ?? [];
  // A run can target several equivalent outputs, each compiled into its own plasmids.
  const outputs = [...new Set(items.map(outputOf).filter(Boolean))] as string[];
  const visible = items.filter(
    (c) => passesFilters(c, filters) && (!outputFilter || outputOf(c) === outputFilter),
  );

  useEffect(() => {
    if (!selectedId && visible.length > 0) setSelectedId(visible[0].id);
  }, [selectedId, visible]);

  const detail = useCandidate(selectedId);

  if (candidates.isLoading) return <Loading />;

  return (
    <div className="space-y-6">
      <Panel className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 grid-clinical opacity-60" />
        <div className="relative">
          <SectionHeading
            kicker="Step 04 · Fulfillment"
            title="Ranked Candidates"
            desc={`${items.length} candidates returned. ${visible.length} shown after filters.`}
          />

          {outputs.length > 1 && (
            <div className="mb-6 flex flex-wrap items-center gap-2">
              <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                Output
              </span>
              {[null, ...outputs].map((output) => (
                <button
                  key={output ?? "all"}
                  onClick={() => setOutputFilter(output)}
                  className={`rounded-md border px-3 py-1 text-xs transition ${
                    outputFilter === output
                      ? "border-mint bg-mint/10 text-mint"
                      : "border-border bg-surface text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {output ?? `All (${items.length})`}
                  {output && (
                    <span className="ml-1.5 opacity-60">
                      {items.filter((c) => outputOf(c) === output).length}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-[1.15fr_1fr]">
            <div className="rounded-2xl border border-border bg-gradient-to-br from-surface to-card p-6">
              {detail.data ? (
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

                  <div className="mt-6 rounded-xl border border-border bg-card p-4">
                    <div className="mb-3 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                      Score decomposition
                    </div>
                    <MetricGrid metrics={detail.data.metrics} />
                  </div>

                  <div className="mt-4 rounded-xl border border-border bg-card p-3">
                    <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                      Switch sequence 5&rsquo; → 3&rsquo;
                    </div>
                    <div className="mt-1 break-all font-mono text-[11px] text-foreground">
                      {detail.data.design.switch_sequence}
                    </div>
                  </div>
                </>
              ) : (
                <Loading />
              )}
            </div>

            <div>
              <PrecisionFilters filters={filters} onChange={setFilters} />

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

          <div className="mt-8 flex flex-col gap-3 border-t border-border pt-6 sm:flex-row">
            <a
              href={api.url(`/runs/${runId}/export.csv`)}
              className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-border bg-card px-6 py-4 text-sm font-medium text-foreground transition hover:border-foreground/30 hover:bg-surface"
            >
              <Download className="h-4 w-4" />
              Export candidates (CSV)
            </a>
            <button
              disabled
              title="Partner integration is not available yet"
              className="group inline-flex flex-[1.4] cursor-not-allowed items-center justify-center gap-3 rounded-xl bg-gradient-deep px-6 py-4 text-sm font-semibold text-primary-foreground opacity-50"
            >
              <ShoppingCart className="h-4 w-4" />
              Order Plasmid with Our Trusted Partner
            </button>
          </div>
        </div>
      </Panel>

      {artifacts.data && artifacts.data.length > 0 && (
        <Panel>
          <SectionHeading
            kicker="Artifacts"
            title="Generated files"
            desc="Sequences and design tables produced by the engine for this run."
          />
          <div className="grid gap-2 sm:grid-cols-2">
            {artifacts.data.map((artifact) => (
              <a
                key={artifact.id}
                href={artifact.download_url}
                className="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3 hover:border-mint"
              >
                <Download className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-mono text-xs text-foreground">
                    {artifact.kind}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    {(artifact.size_bytes / 1024).toFixed(1)} KB
                  </div>
                </div>
              </a>
            ))}
          </div>
        </Panel>
      )}
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
    genes: genes.map((g) => ({ n: g.name, role: g.role, state: g.state, dir: g.direction })),
    midGate: graph?.mid_gate ?? "AND",
    outerGate: graph?.outer_gate ?? "AND",
    invert: graph?.invert ?? false,
    output: graph?.output ?? "GFP",
    caption: graph?.caption ?? "",
  };
}

/** What a candidate expresses. Resolved by the API from design.logic_graph.output. */
const outputOf = (candidate: Candidate) => candidate.output;

function passesFilters(candidate: Candidate, filters: Filters) {
  if (!filters.includeRejected && candidate.is_rejected) return false;
  const score = candidate.overall_score;
  if (score !== null && score * 100 < filters.minScore) return false;
  return true;
}
