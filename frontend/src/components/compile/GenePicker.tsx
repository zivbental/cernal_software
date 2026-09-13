/**
 * "Select a Specific Gene" — informational only (docs/public-datasets.md §16, and the
 * deliberate decision to not add a gene->sequence lookup this round). Records which
 * gene the researcher has in mind, then hands them to "direct" mode to paste its actual
 * sequence — CERNAL has no way to resolve a gene id to an mRNA sequence today.
 */

import { ArrowRight, Sparkles } from "lucide-react";
import { useState } from "react";

import type { Organism } from "@/components/compile/Steps";
import { ORGANISM_LABELS } from "@/components/compile/Steps";

export interface TargetGene {
  organism: Organism;
  geneId: string;
  geneSymbol: string;
}

export function GenePicker({
  organism,
  targetGene,
  onSetGene,
  onContinue,
}: {
  organism: Organism;
  targetGene: TargetGene | null;
  onSetGene: (gene: TargetGene) => void;
  onContinue: () => void;
}) {
  const [geneId, setGeneId] = useState(targetGene?.geneId ?? "");
  const [geneSymbol, setGeneSymbol] = useState(targetGene?.geneSymbol ?? "");

  const canContinue = geneId.trim().length > 0;

  function commitAndContinue() {
    if (!canContinue) return;
    onSetGene({ organism, geneId: geneId.trim(), geneSymbol: geneSymbol.trim() });
    onContinue();
  }

  return (
    <div className="rounded-xl border-2 border-dashed border-border bg-surface p-6">
      <div className="flex items-start gap-4">
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-lg bg-gradient-mint shadow-mint">
          <Sparkles className="h-5 w-5 text-mint-foreground" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold text-foreground">
            I already know my target gene
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            This records the gene for reference on your submission — CERNAL cannot look
            up a sequence from an identifier yet, so you'll paste the transcript
            yourself on the next screen.
          </p>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                Organism
              </span>
              <div className="rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground">
                {ORGANISM_LABELS[organism]}
              </div>
            </label>
            <label className="block">
              <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                Gene ID or symbol
              </span>
              <input
                value={geneId}
                onChange={(e) => setGeneId(e.target.value)}
                placeholder={
                  organism === "human" ? "SELE" : organism === "yeast" ? "CDC28" : "thrA"
                }
                className="w-full rounded-md border border-border bg-card px-3 py-2 font-mono text-xs text-foreground focus:border-mint focus:outline-none"
              />
            </label>
          </div>

          <label className="mt-4 block">
            <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              Display name (optional)
            </span>
            <input
              value={geneSymbol}
              onChange={(e) => setGeneSymbol(e.target.value)}
              placeholder="e.g. a common name, if different from above"
              className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-mint focus:outline-none"
            />
          </label>

          <button
            type="button"
            disabled={!canContinue}
            onClick={commitAndContinue}
            className="mt-4 inline-flex items-center gap-2 rounded-md bg-gradient-mint px-4 py-2 text-sm font-medium text-mint-foreground shadow-mint disabled:cursor-not-allowed disabled:opacity-50"
          >
            Continue — paste its sequence
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
