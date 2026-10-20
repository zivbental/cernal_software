import { createFileRoute } from "@tanstack/react-router";
import { ChevronDown, Lightbulb } from "lucide-react";
import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Panel } from "@/components/layout/Primitives";

export const Route = createFileRoute("/use-cases")({
  component: () => (
    <RequireAuth>
      <AppShell>
        <UseCasesContent />
      </AppShell>
    </RequireAuth>
  ),
});

const USE_CASES = [
  {
    id: "substance-biosensor",
    audience: "For biosensor designers",
    title: "Explore a biosensor concept for a substance",
    summary: "Start from a cell's measured response to a molecule, then explore RNA switches for a known response transcript.",
    input: "A differential-expression comparison between exposed and control cells, or the exact response transcript if already known.",
    output: "Ranked candidate switches for the transcript-level response.",
    limit: "CERNAL does not discover molecule-binding sensors or show that a design detects the substance. The biological response must already be measured and validated.",
    href: "/compile",
    link: "Start a design",
    open: true,
  },
  {
    id: "known-transcript",
    audience: "For molecular biologists",
    title: "Explore a known transcript",
    summary: "Skip gene discovery and inspect candidate switch designs for one transcript.",
    input: "The exact trigger mRNA sequence pasted into Direct Trigger mRNA.",
    output: "Ranked candidates and the diagrams and files available for the run.",
    limit: "A gene label alone does not retrieve a sequence. This is a single-transcript workflow.",
    href: "/compile",
    link: "Use direct input",
  },
  {
    id: "de-comparison",
    audience: "For computational biologists",
    title: "Start from a gene-expression comparison",
    summary: "Rank trigger candidates from a target-versus-control comparison.",
    input: "A catalog comparison or a UTF-8 CSV/TSV table with a gene identifier and log2 fold-change column.",
    output: "Ranked candidates with the available result files.",
    limit: "The current analysis engine supports selected organisms and data formats. Upload acceptance does not prove the engine can use a file.",
    href: "/compile",
    link: "Prepare a comparison",
  },
  {
    id: "two-input-and",
    audience: "For two-input RNA gate designers",
    title: "Design one gate for two chosen input genes",
    summary: "Find switches intended to activate when both selected RNA inputs are present.",
    input: "A differential-expression table and two up-regulated genes. Bacterial AND uses E. coli; eukaryotic AND supports Human and yeast.",
    output: "Ranked candidates, four-state structural diagnostics, rejection reasons and available sequence exports.",
    limit: "Bacterial AND models the complete switch through its linker. The exported construct includes the output CDS; predicted AND behavior requires experimental testing.",
    href: "/compile",
    link: "Configure a two-input gate",
  },
  {
    id: "api-runs",
    audience: "For developers and platform teams",
    title: "Automate repeat runs with the API",
    summary: "Submit, poll, compare, and download runs from Python, R, MATLAB, or curl.",
    input: "An API key and the same input and settings used by the browser workflow.",
    output: "Run status, candidates, and the files made available for that run.",
    limit: "Repeating a request does not guarantee identical output across different engine versions or environments.",
    href: "/api-docs",
    link: "Open the API Reference",
  },
] as const;

export function UseCasesContent() {
  return (
    <>
      <PageHeader
        kicker={
          <>
            <Lightbulb className="h-3 w-3" /> Use Cases
          </>
        }
        title="Choose a starting point"
        description="Suggested workflows for common research roles. Expand one to see what you need and what CERNAL can return."
      />
      <p className="mb-5 rounded-xl border border-border bg-surface p-4 text-sm text-muted-foreground">
        Current scope: the analysis engine designs from one transcript or selects single-gene triggers from expression data. Multi-gene Boolean circuit design is not available yet.
      </p>
      <div className="space-y-3">
        {USE_CASES.map((item) => (
          <Panel key={item.id} className="!p-0">
            <details open={"open" in item ? item.open : false} id={item.id} className="group scroll-mt-24">
              <summary className="flex cursor-pointer list-none items-center gap-4 rounded-xl p-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint [&::-webkit-details-marker]:hidden">
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-[10px] uppercase tracking-wider text-mint">{item.audience}</div>
                  <h2 className="mt-1 text-lg font-semibold text-foreground">{item.title}</h2>
                  <p className="mt-1 text-sm text-muted-foreground">{item.summary}</p>
                </div>
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
              </summary>
              <div className="border-t border-border px-5 pb-5 pt-4">
                <dl className="grid gap-4 text-sm sm:grid-cols-3">
                  {[
                    ["What you need", item.input],
                    ["What you get", item.output],
                    ["Current limits", item.limit],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt className="font-medium text-foreground">{label}</dt>
                      <dd className="mt-1 text-muted-foreground">{value}</dd>
                    </div>
                  ))}
                </dl>
                <a
                  href={item.href}
                  className="mt-5 inline-flex rounded-lg bg-gradient-mint px-4 py-2 text-sm font-medium text-mint-foreground hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint"
                >
                  {item.link} →
                </a>
              </div>
            </details>
          </Panel>
        ))}
      </div>
      <Panel className="mt-6">
        <h2 className="text-lg font-semibold text-foreground">How to read a result</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Rankings help compare candidates for follow-up work. They do not establish experimental validation, a success probability, clinical suitability, proof of safety, specificity, or a complete orderable vector. The current engine does not run a transcriptome-wide off-target scan.
        </p>
      </Panel>
    </>
  );
}
