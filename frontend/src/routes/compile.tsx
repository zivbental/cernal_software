import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { CircuitBoard, LayoutDashboard, Loader2 } from "lucide-react";

import { ApiError } from "@/api/client";
import {
  useDatasets,
  useExampleDatasets,
  useProject,
  useSubmitRun,
  useUploadDataset,
  useUseExampleDataset,
  useVersion,
} from "@/api/queries";
import type { RunParams } from "@/api/types";
import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { StepRail } from "@/components/layout/Primitives";
import {
  DEFAULT_CONFIG,
  StepInputs,
  StepLogic,
  StepPayload,
  type CompileConfig,
} from "@/components/compile/Steps";
import { Loading } from "@/components/layout/Loading";
import { ProjectPicker } from "@/components/compile/ProjectPicker";

export const Route = createFileRoute("/compile")({
  validateSearch: (search: Record<string, unknown>): { projectId?: string } =>
    typeof search.projectId === "string" ? { projectId: search.projectId } : {},
  component: () => (
    <RequireAuth>
      <AppShell>
        <CompilePage />
      </AppShell>
    </RequireAuth>
  ),
});

/** A fresh key per wizard session, so a network retry cannot start a second run. */
function newIdempotencyKey() {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 32);
}

function CompilePage() {
  const { projectId } = Route.useSearch();
  const navigate = useNavigate();

  const project = useProject(projectId ?? "");
  const datasets = useDatasets(projectId ?? "");
  const version = useVersion();
  const upload = useUploadDataset(projectId ?? "");
  const examples = useExampleDatasets();
  const useExample = useUseExampleDataset(projectId ?? "");
  const submit = useSubmitRun(projectId ?? "");

  const [config, setConfig] = useState<CompileConfig>(DEFAULT_CONFIG);
  const [idempotencyKey] = useState(newIdempotencyKey);
  const patch = (p: Partial<CompileConfig>) => setConfig((c) => ({ ...c, ...p }));

  // Memoized so the blocker useMemo below is not invalidated on every render.
  const families = useMemo(() => version.data?.gate_families ?? [], [version.data]);

  const blocker = useMemo(() => {
    if (!projectId) return "Choose a project first.";
    if (config.inputMode === "de") {
      if (!config.datasetId) return "Upload or select a dataset to analyse.";
      const chosen = datasets.data?.find((d) => d.id === config.datasetId);
      if (chosen && chosen.validation_status !== "VALID")
        return "That dataset did not pass validation.";
    } else if (config.triggerSequence.length < 20) {
      return "Paste a trigger sequence of at least 20 nucleotides.";
    }
    if (!families.some((f) => f.name === config.mechanism && f.available))
      return "Choose an available switch mechanism.";
    if (config.outputs.length === 0) return "Choose at least one downstream output.";
    if (config.outputs.includes("other") && config.customPayload.length < 3)
      return "Paste a sequence for your custom output, or deselect it.";
    return null;
  }, [projectId, config, datasets.data, families]);

  const failed = upload.error ?? useExample.error;
  const uploadError =
    failed instanceof ApiError ? failed.message : failed ? "Could not load that dataset." : null;
  const submitError = submit.error instanceof ApiError ? submit.error.message : null;

  async function onSubmit() {
    if (!projectId || blocker) return;

    const params: RunParams = {
      schema_version: "1",
      organism: config.organism,
      input_mode: config.inputMode,
      logic: {
        set_a: config.setA.split(",").map((s) => s.trim()).filter(Boolean),
        set_b: config.setB.split(",").map((s) => s.trim()).filter(Boolean),
        expression: config.setB.trim() ? "A AND NOT B" : "A",
      },
      mechanism: config.mechanism,
      payload: {
        outputs: config.outputs,
        custom_sequence: config.customPayload || null,
      },
      constraints: config.constraints,
      // Makes progress observable while the science is still mocked.
      mock: { candidate_count: 24, step_delay: 0.6 },
    };

    const run = await submit.mutateAsync({
      input_mode: config.inputMode,
      dataset_id: config.inputMode === "de" ? config.datasetId : null,
      trigger_sequence: config.inputMode === "direct" ? config.triggerSequence : "",
      gate_families: [config.mechanism],
      scoring_profile: version.data?.scoring_profiles[0] ?? "default",
      params,
      idempotency_key: idempotencyKey,
    });

    navigate({ to: "/runs/$runId", params: { runId: run.id } });
  }

  if (!projectId) {
    // Not a dead end: pick or create a project here and carry straight on.
    return (
      <>
        <PageHeader
          kicker={
            <>
              <LayoutDashboard className="h-3 w-3" /> New Circuit
            </>
          }
          title="Biological Compiler"
          description="Translate transcriptomic signals into manufacturable genetic circuits."
        />
        <ProjectPicker
          onPick={(id) => navigate({ to: "/compile", search: { projectId: id } })}
        />
      </>
    );
  }

  if (project.isLoading || version.isLoading) return <Loading />;

  return (
    <>
      <PageHeader
        kicker={
          <>
            <LayoutDashboard className="h-3 w-3" /> {project.data?.name ?? "Project"} / New Circuit
          </>
        }
        title="Biological Compiler"
        description="Translate transcriptomic signals into manufacturable genetic circuits. Inputs → Logic → Payload → Compile."
      />

      <div className="mb-8">
        <StepRail active={blocker ? (config.inputMode === "de" && !config.datasetId ? 1 : 2) : 4} />
      </div>

      <div className="space-y-6">
        <StepInputs
          config={config}
          patch={patch}
          datasets={datasets.data ?? []}
          uploading={upload.isPending}
          uploadError={uploadError}
          onUpload={async (file) => {
            const dataset = await upload.mutateAsync(file);
            patch({ datasetId: dataset.validation_status === "VALID" ? dataset.id : null });
          }}
          examples={examples.data ?? []}
          loadingExample={useExample.isPending}
          onUseExample={async (key) => {
            const dataset = await useExample.mutateAsync(key);
            patch({ datasetId: dataset.id });
          }}
        />

        <StepLogic config={config} patch={patch} families={families} />

        <StepPayload config={config} patch={patch} />

        <div className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-6 shadow-clinical sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">Ready to compile</div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {blocker ?? "Your configuration will be frozen and queued for the engine."}
            </p>
            {submitError && (
              <p role="alert" className="mt-2 text-sm text-destructive">
                {submitError}
              </p>
            )}
          </div>
          <button
            onClick={onSubmit}
            disabled={Boolean(blocker) || submit.isPending}
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-gradient-deep px-6 py-3.5 text-sm font-semibold text-primary-foreground shadow-clinical transition hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submit.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CircuitBoard className="h-4 w-4" />
            )}
            Compile &amp; Optimize
          </button>
        </div>
      </div>
    </>
  );
}
