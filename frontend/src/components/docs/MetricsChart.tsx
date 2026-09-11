/**
 * Horizontal bar chart of the nine DEFAULT_V1 scoring weights (CLAUDE.md §2,
 * src/engine/scoring/profiles.py). One series (weight), so one hue — the direction
 * arrow is typographic, not a second color channel, per the dataviz house rules.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface MetricSpec {
  name: string;
  label: string;
  direction: "higher" | "lower";
  weight: number;
  validRange: [number, number];
  unit: string;
  description: string;
}

export const METRICS: MetricSpec[] = [
  { name: "state_separation", label: "State separation", direction: "higher", weight: 3.0, validRange: [0, 10], unit: "log2 fold", description: "Log2 fold between the base and target expression state." },
  { name: "predicted_leakage", label: "Predicted leakage", direction: "lower", weight: 2.5, validRange: [0, 1], unit: "fraction 0–1", description: "Proxy for OFF-state activation — the trap most worth filtering on." },
  { name: "trigger_accessibility", label: "Trigger accessibility", direction: "higher", weight: 2.0, validRange: [0, 1], unit: "fraction 0–1", description: "Fraction of the trigger region predicted free of self-structure." },
  { name: "gate_folding_energy", label: "Gate folding energy", direction: "lower", weight: 2.0, validRange: [-60, 0], unit: "kcal/mol", description: "Predicted MFE of the gate. More negative is more stable." },
  { name: "dynamic_range", label: "Dynamic range", direction: "higher", weight: 2.0, validRange: [1, 500], unit: "linear fold", description: "Predicted ON/OFF fold change — linear, not log, unlike state separation above." },
  { name: "orthogonality", label: "Orthogonality", direction: "higher", weight: 1.5, validRange: [0, 1], unit: "fraction 0–1", description: "Predicted independence from other gates in the same circuit." },
  { name: "predicted_success_rate", label: "Predicted success rate", direction: "higher", weight: 1.0, validRange: [0, 1], unit: "fraction 0–1", description: "Model confidence the construct behaves as designed in vivo." },
  { name: "circuit_complexity", label: "Circuit complexity", direction: "lower", weight: 1.0, validRange: [1, 10], unit: "component count", description: "Component count penalty. Simpler circuits are easier to build." },
  { name: "gc_content", label: "GC content", direction: "higher", weight: 0.5, validRange: [30, 70], unit: "percent 0–100", description: "Percent GC of the assembled construct. Extremes hurt synthesis." },
];

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: MetricSpec }[] }) {
  if (!active || !payload?.length) return null;
  const m = payload[0].payload;
  return (
    <div className="max-w-[220px] rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-clinical">
      <div className="font-mono font-medium text-foreground">{m.name}</div>
      <div className="mt-1 text-muted-foreground">{m.description}</div>
      <div className="mt-1.5 flex items-center justify-between font-mono text-[11px] text-muted-foreground">
        <span>
          {m.direction === "higher" ? "↑ higher better" : "↓ lower better"} · {m.unit}
        </span>
        <span className="text-foreground">weight {m.weight.toFixed(1)}</span>
      </div>
    </div>
  );
}

export function MetricsChart() {
  const data = [...METRICS].sort((a, b) => b.weight - a.weight);

  return (
    <div style={{ height: 340 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 28, bottom: 4, left: 4 }}>
          <CartesianGrid horizontal={false} stroke="var(--border)" strokeDasharray="0" />
          <XAxis
            type="number"
            domain={[0, 3.4]}
            ticks={[0, 1, 2, 3]}
            tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={148}
            tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--secondary)" }} />
          <Bar dataKey="weight" radius={[0, 4, 4, 0]} maxBarSize={18}>
            {data.map((m) => (
              <Cell key={m.name} fill="var(--mint)" />
            ))}
            <LabelList
              dataKey="weight"
              position="right"
              formatter={(v: number) => v.toFixed(1)}
              style={{ fill: "var(--foreground)", fontSize: 11, fontFamily: "var(--font-mono)" }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
