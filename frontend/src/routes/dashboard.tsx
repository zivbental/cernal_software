import { createFileRoute, Link } from "@tanstack/react-router";
import { CircuitBoard, Library } from "lucide-react";

import { useRecentRuns } from "@/api/queries";
import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Loading } from "@/components/layout/Loading";
import { RunStatusBadge } from "@/components/results/RunStatusBadge";

export const Route = createFileRoute("/dashboard")({
  component: () => (
    <RequireAuth>
      <AppShell>
        <DashboardPage />
      </AppShell>
    </RequireAuth>
  ),
});

function DashboardPage() {
  const runs = useRecentRuns(50);

  return (
    <>
      <PageHeader
        kicker={
          <>
            <Library className="h-3 w-3" /> My Circuits
          </>
        }
        title="Dashboard"
        description="Every circuit you have compiled. Each run stands on its own — pick up where you left off, or start a new one."
        actions={
          <Link
            to="/compile"
            className="inline-flex items-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background hover:opacity-90"
          >
            <CircuitBoard className="h-4 w-4" /> New circuit
          </Link>
        }
      />

      {runs.isLoading ? (
        <Loading />
      ) : runs.data && runs.data.length > 0 ? (
        <div className="overflow-hidden rounded-xl border border-border">
          {runs.data.map((run) => (
            <Link
              key={run.id}
              to="/runs/$runId"
              params={{ runId: run.id }}
              className="flex items-center gap-4 border-b border-border bg-card px-5 py-3 last:border-b-0 hover:bg-surface"
            >
              <span className="font-mono text-xs text-muted-foreground">
                {run.id.slice(0, 8)}
              </span>
              <RunStatusBadge status={run.status} />
              <span className="flex-1 truncate text-sm text-foreground">
                {run.organism || "—"}
              </span>
              <span className="truncate text-sm text-muted-foreground">{run.stage || "—"}</span>
              <span className="font-mono text-[11px] text-muted-foreground">
                {new Date(run.created_at).toLocaleDateString()}
              </span>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyRuns />
      )}
    </>
  );
}

function EmptyRuns() {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-surface p-12 text-center">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-lg bg-gradient-mint shadow-mint">
        <CircuitBoard className="h-5 w-5 text-mint-foreground" />
      </div>
      <h3 className="mt-4 text-base font-semibold text-foreground">No circuits yet</h3>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        Compile your first circuit from a transcriptomic signal or a pasted trigger
        sequence.
      </p>
      <Link
        to="/compile"
        className="mt-5 inline-flex items-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background hover:opacity-90"
      >
        <CircuitBoard className="h-4 w-4" /> Compile your first circuit
      </Link>
    </div>
  );
}
