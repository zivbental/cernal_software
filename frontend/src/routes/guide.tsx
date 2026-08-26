import { createFileRoute } from "@tanstack/react-router";
import { BookOpen } from "lucide-react";

import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Panel } from "@/components/layout/Primitives";

export const Route = createFileRoute("/guide")({
  component: () => (
    <RequireAuth>
      <AppShell>
        <GuidePage />
      </AppShell>
    </RequireAuth>
  ),
});

const SECTIONS = [
  {
    title: "1 · Choose your organism and input mode",
    what: "Pick E. coli, yeast or human, then decide how you are supplying the trigger.",
    why: "RNA switches follow the same thermodynamics in any host, so the organism mostly affects codon and expression assumptions rather than the switch itself.",
    tip: "Use Differential Expression when you want CERNAL to discover triggers from your data. Use Direct Trigger mRNA when you already know the transcript — it skips discovery entirely.",
  },
  {
    title: "2 · Upload your differential expression results",
    what: "One file containing your DE analysis. CSV, TSV or XLSX, up to 100 MB.",
    why: "CERNAL does not run differential expression for you. It takes your results and looks for transcripts that cleanly separate the base state from the target state.",
    tip: "A fold-change column is required. Exports from DESeq2, edgeR and Excel are recognised automatically — log2FoldChange, fold_change and FC all work. Fold change is assumed to be target / control.",
  },
  {
    title: "3 · Describe the logic",
    what: "Set A lists transcripts that must be present. Set B lists transcripts that must be absent.",
    why: "This is the Boolean condition that gates expression. A circuit that fires on inflammation but not in regulatory T cells is 'A AND NOT B'.",
    tip: "Leave both blank to let the engine choose triggers from your data. Only the toehold mechanism is available today; CRISPR and antisense are designed but not yet implemented.",
  },
  {
    title: "4 · Choose the payload",
    what: "What the circuit expresses when it fires: a reporter, a selective marker, or your own sequence.",
    why: "Reporters let you validate the switch visually. Selective markers gate phenotype rather than fluorescence.",
    tip: "GFP plus an antibiotic resistance marker is the usual starting point for validation.",
  },
  {
    title: "5 · Compile and read the results",
    what: "Submission is frozen and queued. The run page updates itself while the engine works.",
    why: "Compilation is not instant, so a run has its own URL. You can close the tab and come back to it, or share the link.",
    tip: "Every candidate shows its full score decomposition, not just a final number. Rejected candidates are kept with the reason they were excluded — turn them on in Precision Filters.",
  },
];

function GuidePage() {
  return (
    <>
      <PageHeader
        kicker={
          <>
            <BookOpen className="h-3 w-3" /> Quick Guide
          </>
        }
        title="How to compile a circuit"
        description="From transcriptomic data to a ranked set of manufacturable designs, in five steps."
      />

      <div className="space-y-6">
        {SECTIONS.map((section) => (
          <Panel key={section.title}>
            <h2 className="text-lg font-semibold tracking-tight text-foreground">
              {section.title}
            </h2>
            <dl className="mt-4 space-y-4">
              {[
                ["What this does", section.what],
                ["Why it matters", section.why],
                ["Tips & how to choose", section.tip],
              ].map(([label, body]) => (
                <div key={label}>
                  <dt className="font-mono text-[11px] uppercase tracking-wider text-mint">
                    {label}
                  </dt>
                  <dd className="mt-1 text-sm text-muted-foreground">{body}</dd>
                </div>
              ))}
            </dl>
          </Panel>
        ))}
      </div>
    </>
  );
}
