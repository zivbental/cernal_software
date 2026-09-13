/**
 * The expression-profile preview (docs/public-datasets.md §13/§14) — shown once any
 * dataset is selected, public or uploaded alike, since both are the same GET
 * /datasets/{id}/preview endpoint. Self-contained: owns its own fetch and its own
 * search/sort/filter state, none of which affects the submission.
 */

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useDatasetPreview } from "@/api/queries";
import type { DatasetPreviewRow } from "@/api/types";

type SortKey = "abs_log2fc" | "significance";
type Direction = "all" | "up" | "down";

export function ExpressionPreview({ datasetId }: { datasetId: string | null }) {
  const preview = useDatasetPreview(datasetId);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("abs_log2fc");
  const [direction, setDirection] = useState<Direction>("all");

  const rows = useMemo(() => {
    const all = preview.data?.rows ?? [];
    const term = search.trim().toLowerCase();
    let filtered = term
      ? all.filter(
          (r) =>
            r.gene_id.toLowerCase().includes(term) ||
            (r.gene_symbol ?? "").toLowerCase().includes(term),
        )
      : all;

    if (direction === "up") filtered = filtered.filter((r) => (r.log2fc ?? 0) > 0);
    if (direction === "down") filtered = filtered.filter((r) => (r.log2fc ?? 0) < 0);

    const bySignificance = (r: DatasetPreviewRow) => r.padj ?? r.pvalue ?? 1;
    const sorted = [...filtered].sort((a, b) =>
      sortKey === "abs_log2fc"
        ? Math.abs(b.log2fc ?? 0) - Math.abs(a.log2fc ?? 0)
        : bySignificance(a) - bySignificance(b),
    );
    return sorted;
  }, [preview.data, search, direction, sortKey]);

  if (!datasetId) return null;

  if (preview.isLoading) {
    return (
      <div className="mt-4 rounded-xl border border-border bg-card p-6 text-sm text-muted-foreground">
        Loading expression profile…
      </div>
    );
  }

  if (preview.isError || !preview.data) {
    return (
      <div className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-xs text-destructive">
        Could not load the expression profile for this dataset.
      </div>
    );
  }

  const { total_rows, truncated } = preview.data;

  return (
    <div className="mt-4 space-y-4 rounded-xl border border-border bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm font-medium text-foreground">
          Loaded {total_rows.toLocaleString()} genes
          {truncated && (
            <span className="ml-2 font-mono text-[11px] text-muted-foreground">
              (showing top {preview.data.rows.length.toLocaleString()} by |log2FC|)
            </span>
          )}
        </div>
      </div>

      <VolcanoPlot rows={preview.data.rows} />

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search gene…"
          className="flex-1 rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-mint focus:outline-none"
        />
        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          className="rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-foreground"
        >
          <option value="abs_log2fc">Sort: |log2FC|</option>
          <option value="significance">Sort: significance</option>
        </select>
        <div className="inline-flex rounded-md border border-border bg-surface p-0.5">
          {(["all", "up", "down"] as const).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDirection(d)}
              className={`rounded px-2.5 py-1 text-[11px] font-medium capitalize transition ${
                direction === d
                  ? "bg-card text-foreground shadow-clinical"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {d}
            </button>
          ))}
        </div>
      </div>

      <div className="max-h-80 overflow-y-auto rounded-lg border border-border">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-surface">
            <tr className="border-b border-border text-[10px] uppercase tracking-wider text-muted-foreground">
              <th className="px-3 py-2 font-mono">Gene</th>
              <th className="px-3 py-2 font-mono">log2FC</th>
              <th className="px-3 py-2 font-mono">FDR</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.gene_id} className="border-b border-border last:border-b-0">
                <td className="px-3 py-1.5">
                  <span className="font-mono text-foreground">
                    {row.gene_symbol || row.gene_id}
                  </span>
                  {row.gene_symbol && (
                    <span className="ml-1.5 font-mono text-[10px] text-muted-foreground">
                      {row.gene_id}
                    </span>
                  )}
                </td>
                <td
                  className={`px-3 py-1.5 font-mono ${
                    (row.log2fc ?? 0) > 0
                      ? "text-mint"
                      : (row.log2fc ?? 0) < 0
                        ? "text-destructive"
                        : "text-foreground"
                  }`}
                >
                  {row.log2fc === null ? "—" : `${row.log2fc > 0 ? "+" : ""}${row.log2fc.toFixed(2)}`}
                </td>
                <td className="px-3 py-1.5 font-mono text-muted-foreground">
                  {row.padj !== null
                    ? row.padj.toExponential(1)
                    : row.pvalue !== null
                      ? `${row.pvalue.toExponential(1)} (p, not FDR)`
                      : "—"}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={3} className="px-3 py-4 text-center text-muted-foreground">
                  No genes match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** log2FC vs -log10(significance) — one series, one hue, per the app's own dataviz
 * conventions (components/docs/MetricsChart.tsx). Genes with no p-value or padj at all
 * (a real, documented provider gap — see docs/public-datasets.md) are left off the
 * plot rather than plotted at a fabricated y=0. */
function VolcanoPlot({ rows }: { rows: DatasetPreviewRow[] }) {
  const points = rows
    .filter((r) => r.log2fc !== null && (r.padj !== null || r.pvalue !== null))
    .map((r) => ({
      x: r.log2fc as number,
      y: -Math.log10(Math.max(r.padj ?? r.pvalue ?? 1, 1e-300)),
      gene: r.gene_symbol || r.gene_id,
    }));

  if (points.length === 0) {
    return (
      <p className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-muted-foreground">
        No p-value or FDR reported for this comparison — volcano plot needs at least one
        to show significance.
      </p>
    );
  }

  return (
    <div style={{ height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="0" />
          <XAxis
            type="number"
            dataKey="x"
            name="log2FC"
            tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="-log10(FDR)"
            tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
          />
          <Tooltip
            cursor={{ stroke: "var(--border)" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as { gene: string; x: number; y: number };
              return (
                <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-clinical">
                  <div className="font-mono font-medium text-foreground">{p.gene}</div>
                  <div className="mt-1 text-muted-foreground">
                    log2FC {p.x.toFixed(2)} · -log10(FDR) {p.y.toFixed(2)}
                  </div>
                </div>
              );
            }}
          />
          <Scatter data={points} fill="var(--mint)" fillOpacity={0.7} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
