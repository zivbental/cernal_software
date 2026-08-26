/**
 * Renders a candidate's score decomposition.
 *
 * Driven entirely by the metric array the API returns, never a hardcoded list. When the
 * scientific team changes the scoring profile in Step 5, this keeps working — a metric
 * with no entry in DISPLAY below simply shows its raw name (docs/step-4-frontend-plan.md §2.5).
 */

import type { Metric } from "@/api/types";

interface Display {
  label: string;
  unit?: string;
  /** How many decimals to show. */
  precision?: number;
  /** Multiply before display, e.g. a 0-1 rate shown as a percentage. */
  scale?: number;
  hint?: string;
}

const DISPLAY: Record<string, Display> = {
  state_separation: {
    label: "Separation",
    precision: 2,
    hint: "Differential expression between base and target state (log2 fold).",
  },
  trigger_accessibility: {
    label: "Accessibility",
    precision: 2,
    hint: "Predicted fraction of the trigger region free of self-structure.",
  },
  gate_folding_energy: {
    label: "MFE",
    unit: " kcal/mol",
    precision: 1,
    hint: "Predicted minimum free energy. More negative is more stable.",
  },
  predicted_leakage: {
    label: "Leakage",
    precision: 2,
    hint: "Proxy for OFF-state activation. Lower is better.",
  },
  orthogonality: {
    label: "Off-target",
    unit: "%",
    scale: 100,
    precision: 0,
    hint: "Predicted independence from other transcripts.",
  },
  gc_content: { label: "GC", unit: "%", precision: 0, hint: "Percent GC of the construct." },
  dynamic_range: { label: "Dyn. range", unit: "×", precision: 0, hint: "Predicted ON/OFF fold change." },
  predicted_success_rate: {
    label: "Success",
    unit: "%",
    scale: 100,
    precision: 0,
    hint: "Model confidence the construct behaves as designed in vivo.",
  },
  circuit_complexity: {
    label: "Complexity",
    precision: 0,
    hint: "Component count. Simpler circuits are easier to build.",
  },
};

function humanize(name: string) {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatMetric(metric: Metric): string {
  if (metric.raw_value === null) return "—";
  const display = DISPLAY[metric.name];
  const value = metric.raw_value * (display?.scale ?? 1);
  return `${value.toFixed(display?.precision ?? 2)}${display?.unit ?? ""}`;
}

export function metricLabel(name: string): string {
  return DISPLAY[name]?.label ?? humanize(name);
}

/** Compact tiles, for a candidate row. */
export function MetricTiles({ metrics }: { metrics: Metric[] }) {
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
      {metrics.map((metric) => (
        <div
          key={metric.name}
          title={DISPLAY[metric.name]?.hint}
          className="rounded-md border border-border bg-card px-2 py-1.5"
        >
          <div className="truncate text-[10px] text-muted-foreground">
            {metricLabel(metric.name)}
          </div>
          <div className="font-mono text-xs font-medium text-foreground">
            {formatMetric(metric)}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Full decomposition with contribution bars, for a candidate's detail panel. */
export function MetricGrid({ metrics }: { metrics: Metric[] }) {
  const totalWeight = metrics.reduce((sum, m) => sum + m.weight, 0) || 1;

  return (
    <div className="space-y-3">
      {metrics.map((metric) => {
        const normalized = metric.normalized_value;
        const share = (metric.weight / totalWeight) * 100;
        return (
          <div key={metric.name}>
            <div className="flex items-baseline justify-between gap-3 text-xs">
              <span className="text-muted-foreground" title={DISPLAY[metric.name]?.hint}>
                {metricLabel(metric.name)}
                <span className="ml-1.5 font-mono text-[10px] opacity-60">
                  {metric.direction === "LOWER_BETTER" ? "↓ better" : "↑ better"}
                </span>
              </span>
              <span className="font-mono text-foreground">{formatMetric(metric)}</span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-border">
                <div
                  className="absolute h-1.5 rounded-full bg-gradient-mint"
                  style={{ width: `${Math.round((normalized ?? 0) * 100)}%` }}
                />
              </div>
              <span
                className="w-14 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
                title={`Weight ${metric.weight} of ${totalWeight} (${share.toFixed(0)}%)`}
              >
                {normalized === null ? "n/a" : normalized.toFixed(2)}
              </span>
            </div>
          </div>
        );
      })}
      <p className="pt-1 font-mono text-[10px] text-muted-foreground">
        Normalized 0–1, higher is better in every row. The overall score is the
        weighted mean.
      </p>
    </div>
  );
}
