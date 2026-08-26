import { createFileRoute, Link } from "@tanstack/react-router";
import { CircuitBoard, Database, FlaskConical } from "lucide-react";

import { useDatasets, useProject, useProjectRuns } from "@/api/queries";
import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { RunStatusBadge } from "@/components/results/RunStatusBadge";
import { Loading } from "@/components/layout/Loading";

export const Route = createFileRoute("/projects/$projectId")({
  component: () => (
    <RequireAuth>
      <AppShell>
        <ProjectDetail />
      </AppShell>
    </RequireAuth>
  ),
});

function ProjectDetail() {
  const { projectId } = Route.useParams();
  const project = useProject(projectId);
  const datasets = useDatasets(projectId);
  const runs = useProjectRuns(projectId);

  if (project.isLoading) return <Loading />;
  if (!project.data) {
    return <p className="text-sm text-muted-foreground">That project could not be found.</p>;
  }

  return (
    <>
      <PageHeader
        kicker={
          <>
            <FlaskConical className="h-3 w-3" />
            <Link to="/projects" className="hover:text-foreground">
              Projects
            </Link>
            <span>/</span>
            {project.data.organism}
          </>
        }
        title={project.data.name}
        description={project.data.biological_objective}
        actions={
          <Link
            to="/compile"
            search={{ projectId }}
            className="inline-flex items-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background hover:opacity-90"
          >
            <CircuitBoard className="h-4 w-4" /> New circuit
          </Link>
        }
      />

      <div className="grid gap-8 lg:grid-cols-2">
        <section>
          <h2 className="mb-3 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            <Database className="h-3 w-3" /> Datasets
          </h2>
          {datasets.data?.length ? (
            <div className="overflow-hidden rounded-xl border border-border">
              {datasets.data.map((dataset) => (
                <div
                  key={dataset.id}
                  className="flex items-center gap-3 border-b border-border bg-card px-4 py-3 last:border-b-0"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-mono text-xs text-foreground">
                      {dataset.name}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {dataset.validation_report?.rows ?? 0} rows ·{" "}
                      {(dataset.size_bytes / 1024).toFixed(0)} KB
                    </div>
                  </div>
                  <span
                    className={`rounded-md px-2 py-0.5 font-mono text-[10px] ${
                      dataset.validation_status === "VALID"
                        ? "bg-mint/10 text-mint"
                        : "bg-destructive/10 text-destructive"
                    }`}
                  >
                    {dataset.validation_status}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyPanel text="No datasets uploaded yet." />
          )}
        </section>

        <section>
          <h2 className="mb-3 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            <CircuitBoard className="h-3 w-3" /> Runs
          </h2>
          {runs.data?.length ? (
            <div className="overflow-hidden rounded-xl border border-border">
              {runs.data.map((run) => (
                <Link
                  key={run.id}
                  to="/runs/$runId"
                  params={{ runId: run.id }}
                  className="flex items-center gap-3 border-b border-border bg-card px-4 py-3 last:border-b-0 hover:bg-surface"
                >
                  <span className="font-mono text-xs text-muted-foreground">
                    {run.id.slice(0, 8)}
                  </span>
                  <RunStatusBadge status={run.status} />
                  <span className="flex-1 truncate text-sm text-foreground">
                    {run.stage || "—"}
                  </span>
                  <span className="font-mono text-[11px] text-muted-foreground">
                    {new Date(run.created_at).toLocaleDateString()}
                  </span>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyPanel text="No runs yet — compile your first circuit." />
          )}
        </section>
      </div>
    </>
  );
}

function EmptyPanel({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-surface p-8 text-center text-sm text-muted-foreground">
      {text}
    </div>
  );
}
