/**
 * Renders a candidate's score decomposition.
 *
 * Driven entirely by the metric array the API returns, never a hardcoded list. When the
 * scientific team changes the scoring profile in Step 5, this keeps working — a metric
 * with no entry in DISPLAY below simply shows its raw name (docs/architecture.md §8).
 */

import type { Metric } from "@/api/types";
import { CircleHelp } from "lucide-react";
import { useId, useState } from "react";

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
    hint: "Minimum marginal unpaired probability across the trigger region.",
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
    label: "Orthogonality",
    unit: "%",
    scale: 100,
    precision: 0,
    hint: "Unmeasured: no transcriptome-wide off-target scan is integrated.",
  },
  gc_content: { label: "GC", unit: "%", precision: 0, hint: "Percent GC of the switch sequence." },
  dynamic_range: { label: "Accessibility ratio", unit: "×", precision: 0, hint: "Initiation accessibility ratio (proxy), not measured expression fold change." },
  predicted_success_rate: {
    label: "Binding heuristic",
    unit: "%",
    scale: 100,
    precision: 0,
    hint: "Binding energy heuristic (uncalibrated); not an in-vivo success probability.",
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
  if (metric.raw_value === null || !Number.isFinite(metric.raw_value)) return "Unmeasured";
  const display = DISPLAY[metric.name];
  const value = metric.raw_value * (display?.scale ?? 1);
  return `${value.toFixed(display?.precision ?? 2)}${display?.unit ?? ""}`;
}

export function metricLabel(name: string): string {
  return DISPLAY[name]?.label ?? humanize(name);
}

/** Compact tiles, for a candidate row. */
export function MetricTiles({ metrics }: { metrics: Metric[] }) {
  const [openMetric, setOpenMetric] = useState<string | null>(null);
  const instanceId = useId();
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
      {metrics.map((metric) => {
        const helpId = `${instanceId}-metric-help-${metric.name}`;
        const description = DISPLAY[metric.name]?.hint
          ?? "This value is reported by the active scoring profile; its meaning depends on that metric definition.";
        return (
          <div key={metric.name} className="rounded-md border border-border bg-card px-2 py-1.5">
            <div className="truncate text-[10px] text-muted-foreground">
              {metricLabel(metric.name)}
            </div>
            <div className="flex items-center gap-1 font-mono text-xs font-medium text-foreground">
              <span>{formatMetric(metric)}</span>
              <button
                type="button"
                aria-label={`Explain ${metricLabel(metric.name)}`}
                aria-expanded={openMetric === metric.name}
                aria-controls={helpId}
                onClick={() => setOpenMetric((current) => current === metric.name ? null : metric.name)}
                className="rounded-full p-0.5 text-muted-foreground transition hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint"
              >
                <CircleHelp className="h-3.5 w-3.5" />
              </button>
            </div>
            {openMetric === metric.name && (
              <p id={helpId} className="mt-1.5 text-[10px] leading-relaxed text-muted-foreground">
                {description}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Full decomposition with contribution bars, for a candidate's detail panel. */
export function MetricGrid({ metrics }: { metrics: Metric[] }) {
  const [openMetric, setOpenMetric] = useState<string | null>(null);
  const instanceId = useId();
  const totalWeight = metrics.reduce((sum, m) => sum + m.weight, 0) || 1;

  return (
    <div className="space-y-3">
      {metrics.map((metric) => {
        const normalized = metric.normalized_value;
        const share = (metric.weight / totalWeight) * 100;
        const description = DISPLAY[metric.name]?.hint
          ?? "This value is reported by the active scoring profile; its meaning depends on that metric definition.";
        const helpId = `${instanceId}-metric-help-${metric.name}`;
        return (
          <div key={metric.name}>
            <div className="flex items-baseline justify-between gap-3 text-xs">
              <span className="inline-flex min-w-0 items-center gap-1.5 text-muted-foreground">
                <span>{metricLabel(metric.name)}</span>
                <span className="ml-1.5 font-mono text-[10px] opacity-60">
                  {metric.direction === "LOWER_BETTER" ? "↓ better" : "↑ better"}
                </span>
              </span>
              <span className="inline-flex shrink-0 items-center gap-1.5">
                <span className="font-mono text-foreground">{formatMetric(metric)}</span>
                <button
                  type="button"
                  aria-label={`Explain ${metricLabel(metric.name)}`}
                  aria-expanded={openMetric === metric.name}
                  aria-controls={helpId}
                  onClick={() => setOpenMetric((current) => current === metric.name ? null : metric.name)}
                  className="rounded-full p-0.5 text-muted-foreground transition hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint"
                >
                  <CircleHelp className="h-3.5 w-3.5" />
                </button>
              </span>
            </div>
            {openMetric === metric.name && (
              <p id={helpId} className="mt-2 rounded-md bg-secondary/70 px-2.5 py-2 text-[11px] leading-relaxed text-muted-foreground">
                {description} This metric contributes {share.toFixed(0)}% of the weighted score.
                {normalized !== null && ` Its normalized value is ${normalized.toFixed(2)} on a 0–1 scale.`}
              </p>
            )}
            <div className="mt-1 flex items-center gap-2">
              <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-border">
                <div
                  className="absolute h-1.5 rounded-full bg-gradient-mint"
                  style={{ width: `${Math.round((normalized ?? 0) * 100)}%` }}
                />
              </div>
              <span
                className="w-14 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
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
