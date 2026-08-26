import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { CircuitBoard, FolderPlus, Library } from "lucide-react";

import { ApiError } from "@/api/client";
import { useCreateProject, useProjects, useRecentRuns } from "@/api/queries";
import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Loading } from "@/components/layout/Loading";
import { RunStatusBadge } from "@/components/results/RunStatusBadge";

export const Route = createFileRoute("/projects")({
  component: () => (
    <RequireAuth>
      <AppShell>
        <ProjectsPage />
      </AppShell>
    </RequireAuth>
  ),
});

function ProjectsPage() {
  const projects = useProjects();
  const runs = useRecentRuns(8);
  const [creating, setCreating] = useState(false);

  return (
    <>
      <PageHeader
        kicker={
          <>
            <Library className="h-3 w-3" /> My Circuits
          </>
        }
        title="Projects"
        description="Each project holds a biological objective, its datasets, and every analysis run against them."
        actions={
          <>
            <button
              onClick={() => setCreating(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm text-foreground hover:border-mint"
            >
              <FolderPlus className="h-4 w-4" /> New project
            </button>
            <Link
              to="/compile"
              className="inline-flex items-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background hover:opacity-90"
            >
              <CircuitBoard className="h-4 w-4" /> New circuit
            </Link>
          </>
        }
      />

      {creating && <NewProjectForm onDone={() => setCreating(false)} />}

      {projects.isLoading ? (
        <Loading />
      ) : projects.data && projects.data.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.data.map((project) => (
            <Link
              key={project.id}
              to="/projects/$projectId"
              params={{ projectId: project.id }}
              className="rounded-2xl border border-border bg-card p-6 shadow-clinical transition hover:border-mint"
            >
              <div className="font-mono text-[11px] uppercase tracking-wider text-mint">
                {project.organism}
              </div>
              <h3 className="mt-1 text-base font-semibold text-foreground">{project.name}</h3>
              {project.biological_objective && (
                <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
                  {project.biological_objective}
                </p>
              )}
              <div className="mt-4 flex gap-4 font-mono text-[11px] text-muted-foreground">
                <span>{project.dataset_count} datasets</span>
                <span>{project.run_count} runs</span>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        !creating && <EmptyProjects onCreate={() => setCreating(true)} />
      )}

      {runs.data && runs.data.length > 0 && (
        <section className="mt-12">
          <h2 className="mb-4 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            Recent runs
          </h2>
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
                <span className="flex-1 truncate text-sm text-foreground">{run.stage || "—"}</span>
                <span className="font-mono text-[11px] text-muted-foreground">
                  {new Date(run.created_at).toLocaleDateString()}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

function NewProjectForm({ onDone }: { onDone: () => void }) {
  const create = useCreateProject();
  const [name, setName] = useState("");
  const [organism, setOrganism] = useState("E. coli");
  const [objective, setObjective] = useState("");

  const message = create.error instanceof ApiError ? create.error.message : null;

  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        await create.mutateAsync({ name, organism, biological_objective: objective });
        onDone();
      }}
      className="mb-8 rounded-2xl border border-border bg-card p-6 shadow-clinical"
    >
      <h2 className="text-base font-semibold text-foreground">New project</h2>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            Name
          </span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            autoFocus
            className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-mint focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            Organism
          </span>
          <input
            value={organism}
            onChange={(e) => setOrganism(e.target.value)}
            required
            className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-mint focus:outline-none"
          />
        </label>
      </div>
      <label className="mt-4 block">
        <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          Biological objective
        </span>
        <textarea
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
          rows={2}
          placeholder="Base state, target state, and the logic behaviour you are designing for."
          className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-mint focus:outline-none"
        />
      </label>

      {message && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {message}
        </p>
      )}

      <div className="mt-5 flex gap-2">
        <button
          type="submit"
          disabled={create.isPending}
          className="rounded-lg bg-gradient-deep px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-60"
        >
          {create.isPending ? "Creating…" : "Create project"}
        </button>
        <button
          type="button"
          onClick={onDone}
          className="rounded-lg border border-border bg-card px-4 py-2 text-sm text-foreground"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function EmptyProjects({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-surface p-12 text-center">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-lg bg-gradient-mint shadow-mint">
        <CircuitBoard className="h-5 w-5 text-mint-foreground" />
      </div>
      <h3 className="mt-4 text-base font-semibold text-foreground">No projects yet</h3>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        A project is where a biological objective, its transcriptomic data and its
        compiled circuits live together.
      </p>
      <button
        onClick={onCreate}
        className="mt-5 inline-flex items-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background hover:opacity-90"
      >
        <FolderPlus className="h-4 w-4" /> Create your first project
      </button>
    </div>
  );
}

