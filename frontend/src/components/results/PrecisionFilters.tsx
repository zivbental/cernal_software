/**
 * Client-side refinement of an already-fetched candidate list.
 *
 * Deliberately not a server round-trip: a run returns a few hundred candidates, so
 * filtering in memory is instant and keeps scores comparable across runs
 * (docs/step-4-frontend-plan.md §3, decision 7).
 */

import { ChevronDown, Sparkles } from "lucide-react";
import { useState } from "react";

import { SliderRow } from "@/components/compile/Bits";

export interface Filters {
  minScore: number;
  includeRejected: boolean;
  sort: string;
}

export const DEFAULT_FILTERS: Filters = {
  minScore: 0,
  includeRejected: false,
  sort: "rank",
};

const SORTS = [
  { value: "rank", label: "Rank" },
  { value: "-overall_score", label: "Score (high → low)" },
  { value: "gate_family", label: "Gate family" },
  { value: "engine_ref", label: "Identifier" },
];

export function PrecisionFilters({
  filters,
  onChange,
}: {
  filters: Filters;
  onChange: (filters: Filters) => void;
}) {
  const [open, setOpen] = useState(false);
  const patch = (p: Partial<Filters>) => onChange({ ...filters, ...p });

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-3 text-left transition hover:bg-surface"
      >
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-mint" />
          <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            Precision Filters
          </span>
        </div>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="space-y-4 border-t border-border p-5">
          <label className="block">
            <span className="mb-1.5 block text-xs text-muted-foreground">Sort by</span>
            <select
              value={filters.sort}
              onChange={(e) => patch({ sort: e.target.value })}
              className="w-full rounded-md border border-border bg-card px-3 py-1.5 text-xs text-foreground focus:border-mint focus:outline-none"
            >
              {SORTS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <SliderRow
            label="Minimum score"
            value={filters.minScore}
            min={0}
            max={100}
            unit="%"
            onChange={(v) => patch({ minScore: v })}
          />

          <label className="flex cursor-pointer items-center justify-between gap-3 text-xs">
            <span className="text-muted-foreground">
              Show rejected candidates
              <span className="mt-0.5 block text-[10px] opacity-70">
                Every rejection carries a reason.
              </span>
            </span>
            <input
              type="checkbox"
              checked={filters.includeRejected}
              onChange={(e) => patch({ includeRejected: e.target.checked })}
              className="h-4 w-4 accent-[var(--mint)]"
            />
          </label>
        </div>
      )}
    </div>
  );
}
