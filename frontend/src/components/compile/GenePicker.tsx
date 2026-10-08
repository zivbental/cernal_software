import { ArrowRight, Sparkles } from "lucide-react";
import { useRef, useState } from "react";

import { api } from "@/api/client";
import type { Organism } from "@/components/compile/Steps";
import { ORGANISM_LABELS } from "@/components/compile/Steps";

export interface TargetGene {
  organism: Organism;
  geneId: string;
  geneSymbol: string;
}
interface ReferenceGene {
  gene_id: string;
  gene_symbol: string;
  sequence: string;
  transcript_id: string;
  selection_method: string;
}

export function GenePicker({ organism, targetGene, onSetGene, onContinue }: {
  organism: Organism;
  targetGene: TargetGene | null;
  onSetGene: (gene: TargetGene | null) => void;
  onContinue: (sequence: string) => void;
}) {
  const [geneId, setGeneId] = useState(targetGene?.geneId ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolved, setResolved] = useState<ReferenceGene | null>(null);
  const revision = useRef(0);

  async function resolve() {
    const submittedRevision = revision.current;
    setBusy(true);
    setError(null);
    try {
      const ref = await api.get<ReferenceGene>(`/reference-genes/resolve?organism=${organism}&gene=${encodeURIComponent(geneId.trim())}`);
      if (submittedRevision !== revision.current) return;
      onSetGene({ organism, geneId: ref.gene_id, geneSymbol: ref.gene_symbol });
      onContinue(ref.sequence);
      setResolved(ref);
    } catch (err) {
      if (submittedRevision === revision.current)
        setError(err instanceof Error ? err.message : "Could not resolve this gene.");
    } finally { setBusy(false); }
  }

  return (
    <div className="rounded-xl border-2 border-dashed border-border bg-surface p-6">
      <div className="flex items-start gap-4">
        <Sparkles className="h-5 w-5 shrink-0 text-mint" />
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold">I already know my target gene</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Look up a stable gene ID or an unambiguous symbol in the bundled {ORGANISM_LABELS[organism]} reference. Human genes use a mature transcript, preferring MANE Select and then Ensembl canonical transcripts.
          </p>
          <label className="mt-4 block">
            <span className="mb-1.5 block text-sm">Gene ID or symbol</span>
            <input value={geneId} onChange={(e) => {
              revision.current += 1;
              setGeneId(e.target.value); setResolved(null); setError(null); onSetGene(null);
            }} placeholder={organism === "human" ? "SELE or ENSG00000007908" : organism === "yeast" ? "CDC28" : organism === "c_acnes" ? "F6X01_RS00005" : "thrA"}
              className="w-full rounded-md border border-border bg-card px-3 py-2 font-mono text-xs" />
          </label>
          <button type="button" disabled={!geneId.trim() || busy} onClick={resolve}
            className="mt-4 inline-flex items-center gap-2 rounded-md bg-gradient-mint px-4 py-2 text-sm font-medium text-mint-foreground disabled:opacity-50">
            {busy ? "Looking up transcript…" : "Resolve reference transcript"}<ArrowRight className="h-3.5 w-3.5" />
          </button>
          {error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}
          {resolved && <p role="status" className="mt-3 text-sm text-muted-foreground">
            {resolved.gene_symbol || resolved.gene_id} · {resolved.transcript_id || resolved.gene_id} · {resolved.sequence.length.toLocaleString()} nucleotides · {resolved.selection_method}
          </p>}
        </div>
      </div>
    </div>
  );
}
