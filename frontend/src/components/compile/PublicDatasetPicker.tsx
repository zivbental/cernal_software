/**
 * "Use a Public Dataset" (docs/public-datasets.md §12) — organism -> experiment ->
 * comparison, an info card, then "Load Expression Profile" materializes it into a real
 * Dataset the same way an example dataset already does (queries.ts's
 * useMaterializePublicDataset). Self-contained: owns its own selection state and data
 * fetching, since nothing outside this component needs it — Steps.tsx just needs to
 * know the resulting datasetId.
 */

import { AlertCircle, ExternalLink, Loader2, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import {
  useMaterializePublicDataset,
  usePublicComparisons,
  usePublicDatasetInfo,
  usePublicExperiments,
} from "@/api/queries";
import type { Organism } from "@/components/compile/Steps";

const ORGANISM_KEY: Record<Organism, string> = { ecoli: "ecoli", yeast: "yeast", human: "human" };

export function PublicDatasetPicker({
  organism,
  onLoaded,
}: {
  organism: Organism;
  onLoaded: (datasetId: string) => void;
}) {
  const [experimentKey, setExperimentKey] = useState<string>("");
  const [comparisonKey, setComparisonKey] = useState<string>("");

  const experiments = usePublicExperiments(ORGANISM_KEY[organism]);
  const comparisons = usePublicComparisons(experimentKey || null);
  const info = usePublicDatasetInfo(comparisonKey || null);
  const materialize = useMaterializePublicDataset();

  // Changing the organism (the wizard's own top-level picker) invalidates any
  // downstream selection — an E. coli comparison key means nothing once "Human" is
  // picked. Re-select from the top rather than silently keeping a stale choice.
  useEffect(() => {
    setExperimentKey("");
    setComparisonKey("");
  }, [organism]);

  const loadError =
    materialize.error instanceof ApiError
      ? materialize.error.message
      : materialize.error
        ? "That dataset could not be loaded."
        : null;

  return (
    <div className="rounded-xl border-2 border-dashed border-border bg-surface p-6">
      <div className="flex items-start gap-4">
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-lg bg-gradient-mint shadow-mint">
          <Sparkles className="h-5 w-5 text-mint-foreground" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold text-foreground">
            A real, published biological state
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Curated from EMBL-EBI Expression Atlas and BV-BRC — every entry keeps its
            source accession, so you always know where it came from.
          </p>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                Experiment
              </span>
              <select
                value={experimentKey}
                onChange={(e) => {
                  setExperimentKey(e.target.value);
                  setComparisonKey("");
                }}
                disabled={experiments.isLoading}
                className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-mint focus:outline-none"
              >
                <option value="">
                  {experiments.isLoading ? "Loading…" : "Choose an experiment…"}
                </option>
                {experiments.data?.map((exp) => (
                  <option key={exp.experiment_key} value={exp.experiment_key}>
                    {exp.title}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                Comparison
              </span>
              <select
                value={comparisonKey}
                onChange={(e) => setComparisonKey(e.target.value)}
                disabled={!experimentKey || comparisons.isLoading}
                className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-mint focus:outline-none disabled:opacity-60"
              >
                <option value="">
                  {!experimentKey
                    ? "Choose an experiment first"
                    : comparisons.isLoading
                      ? "Loading…"
                      : "Choose a comparison…"}
                </option>
                {comparisons.data?.map((cmp) => (
                  <option key={cmp.comparison_key} value={cmp.comparison_key}>
                    {cmp.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {experiments.isError && (
            <p className="mt-3 flex items-center gap-1.5 text-xs text-destructive">
              <AlertCircle className="h-3.5 w-3.5" />
              This public dataset catalog is temporarily unavailable. You can still
              upload your own expression data or select a gene directly.
            </p>
          )}

          {info.data && (
            <div className="mt-5 rounded-lg border border-border bg-card p-4">
              <div className="text-sm font-semibold text-foreground">
                {info.data.experiment_title}
              </div>
              <dl className="mt-3 grid gap-x-4 gap-y-1.5 text-xs sm:grid-cols-2">
                <InfoRow label="Data source" value={PROVIDER_LABELS[info.data.provider] ?? info.data.provider} />
                <InfoRow label="Accession" value={info.data.experiment_accession} mono />
                <InfoRow label="Experimental condition" value={info.data.experimental_condition} />
                <InfoRow label="Reference condition" value={info.data.reference_condition} />
                <InfoRow label="Genes" value={info.data.gene_count.toLocaleString()} />
                {info.data.analysis_method && (
                  <InfoRow label="Analysis method" value={info.data.analysis_method} />
                )}
              </dl>

              {/* §2/§27: the direction of log2FC is the single easiest mistake to make
                  reading differential expression — spell it out explicitly. */}
              <div className="mt-3 rounded-md bg-mint/5 px-3 py-2 font-mono text-[11px] text-muted-foreground">
                <span className="text-mint">Positive</span> log2FC = higher in{" "}
                <span className="text-foreground">{info.data.experimental_condition}</span>
                <br />
                <span className="text-destructive">Negative</span> log2FC = higher in{" "}
                <span className="text-foreground">{info.data.reference_condition}</span>
              </div>

              <a
                href={info.data.source_url}
                target="_blank"
                rel="noreferrer"
                className="mt-3 inline-flex items-center gap-1 text-xs text-mint hover:underline"
              >
                View source <ExternalLink className="h-3 w-3" />
              </a>

              <button
                type="button"
                disabled={materialize.isPending}
                onClick={() =>
                  materialize.mutate(comparisonKey, { onSuccess: (dataset) => onLoaded(dataset.id) })
                }
                className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md bg-gradient-mint px-4 py-2.5 text-sm font-medium text-mint-foreground shadow-mint disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
              >
                {materialize.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                Load Expression Profile
              </button>

              {loadError && (
                <p role="alert" className="mt-2 text-xs text-destructive">
                  {loadError}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const PROVIDER_LABELS: Record<string, string> = {
  expression_atlas: "EMBL-EBI Expression Atlas",
  bvbrc: "BV-BRC",
  yeast_expression: "EMBL-EBI Expression Atlas",
};

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="contents">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={mono ? "font-mono text-foreground" : "text-foreground"}>{value}</dd>
    </div>
  );
}
