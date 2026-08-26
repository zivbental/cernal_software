/**
 * Choosing (or creating) the project a circuit belongs to.
 *
 * The Lovable design jumped straight to compiling, with no notion of a project. But
 * datasets, runs and history all hang off one, so the wizard asks here rather than
 * sending people away to create one first.
 */

import { useState } from "react";
import { FolderPlus, Loader2 } from "lucide-react";

import { ApiError } from "@/api/client";
import { useCreateProject, useProjects } from "@/api/queries";
import { Panel, SectionHeading } from "@/components/layout/Primitives";
import { Check } from "@/components/compile/Bits";

export function ProjectPicker({ onPick }: { onPick: (projectId: string) => void }) {
  const projects = useProjects();
  const create = useCreateProject();

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [organism, setOrganism] = useState("E. coli");
  const [objective, setObjective] = useState("");

  const message = create.error instanceof ApiError ? create.error.message : null;
  const existing = projects.data ?? [];
  // Nothing to choose between, so go straight to the form.
  const showForm = creating || (!projects.isLoading && existing.length === 0);

  return (
    <Panel>
      <SectionHeading
        kicker="Step 00 · Project"
        title="Where should this circuit live?"
        desc="A project holds your biological objective, its datasets, and every circuit compiled against them."
      />

      {projects.isLoading ? (
        <div className="grid place-items-center py-10">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          {existing.length > 0 && (
            <div className="space-y-2">
              {existing.map((project) => (
                <button
                  key={project.id}
                  type="button"
                  onClick={() => onPick(project.id)}
                  className="flex w-full items-center gap-3 rounded-lg border border-border bg-surface p-4 text-left transition hover:border-mint"
                >
                  <Check on={false} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-foreground">
                      {project.name}
                    </div>
                    <div className="font-mono text-[11px] text-muted-foreground">
                      {project.organism} · {project.dataset_count} datasets ·{" "}
                      {project.run_count} runs
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}

          {showForm ? (
            <form
              onSubmit={async (event) => {
                event.preventDefault();
                const project = await create.mutateAsync({
                  name,
                  organism,
                  biological_objective: objective,
                });
                onPick(project.id);
              }}
              className={existing.length > 0 ? "mt-6 border-t border-border pt-6" : "mt-2"}
            >
              <div className="grid gap-4 md:grid-cols-2">
                <label className="block">
                  <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                    Project name
                  </span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    autoFocus
                    placeholder="Inflammation-gated reporter"
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
                  className="inline-flex items-center gap-2 rounded-lg bg-gradient-deep px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-60"
                >
                  {create.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Create and continue
                </button>
                {existing.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setCreating(false)}
                    className="rounded-lg border border-border bg-card px-4 py-2 text-sm text-foreground"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </form>
          ) : (
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="mt-4 inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm text-foreground hover:border-mint"
            >
              <FolderPlus className="h-4 w-4" /> New project
            </button>
          )}
        </>
      )}
    </Panel>
  );
}
