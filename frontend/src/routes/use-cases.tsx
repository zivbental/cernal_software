import { createFileRoute } from "@tanstack/react-router";
import { Lightbulb } from "lucide-react";
import { Caveat } from "@/components/docs/HelpNav";
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

const WORKFLOWS = [
  {
    id: "explore-interface",
    title: "Explore the interface on a small real run",
    goal: "Learn the submission, status, ranking, rejection, and download screens on a run small enough to finish quickly.",
    input:
      "A public dataset or a pasted transcript, on the default LocalEngine installation.",
    output:
      "Real, reproducible candidates and artifacts — the same ones a full run produces, just fewer.",
    limit:
      "Off-target specificity is not established. Available metrics depend on the gate family; a blank value means unmeasured. Candidates are computational designs to test.",
    href: "/guide#before-running",
    next: "Check what the engine supports",
  },
  {
    id: "de-comparison",
    title: "Start from a differential-expression comparison",
    goal: "Rank single-gene trigger candidates from an existing target-versus-control comparison.",
    input:
      "A catalog comparison or a UTF-8 CSV/TSV table with a gene identifier and an explicit log2FoldChange column.",
    output:
      "Ranked candidates, rejection reasons, warnings, and the artifacts actually emitted by the run.",
    limit:
      "Identifiers must resolve in the selected host's bundled reference. Upload acceptance does not prove the engine can scientifically use the table.",
    href: "/guide#choose-input",
    next: "Prepare a DE input",
  },
  {
    id: "known-transcript",
    title: "Start from a known transcript",
    goal: "Skip gene discovery and scan one transcript for candidate trigger windows.",
    input: "The exact trigger mRNA sequence pasted into Direct Trigger mRNA.",
    output:
      "Candidate switches for that transcript, with scores, filters, warnings, and available sequence artifacts.",
    limit:
      "Specific Gene resolves one bundled reference transcript. Direct and Specific Gene input are single-transcript workflows; two-input AND requires DE input and two explicit genes.",
    href: "/guide#choose-input",
    next: "Use direct input",
  },
  {
    id: "two-input-and",
    title: "Design one gate for two chosen input genes",
    goal: "Find RNA switches intended to activate when both selected inputs are present.",
    input: "A differential-expression table and two up-regulated genes from that table. Bacterial AND uses E. coli; eukaryotic AND supports Human and yeast.",
    output: "Ranked candidates, four-state structural diagnostics, feasibility or rejection reasons, and available sequence artifacts with a reproducibility manifest.",
    limit: "Bacterial AND folds the complete switch through its linker, excluding the output CDS. Exported constructs include the complete output; predicted structural AND behavior requires experimental testing.",
    href: "/guide#configure",
    next: "Configure the two-input gate",
  },
  {
    id: "api-runs",
    title: "Repeat and inspect runs through the API",
    goal: "Submit, poll, compare, and download runs from Python, R, MATLAB, or curl.",
    input:
      "An API key plus the same frozen input and parameters used for the browser workflow.",
    output:
      "A run ID, status, candidates, errors, and downloadable artifacts exposed by that run.",
    limit:
      "Idempotency prevents duplicate submission; it does not guarantee byte-identical output across different engines, versions, profiles, or environments.",
    href: "/api-docs",
    next: "Open the API Reference",
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
        title="Choose a supported workflow"
        description="Start with the input you have and the kind of inspection you need."
      />
      <Caveat>
        <strong>Scope:</strong> the current LocalEngine designs from one
        transcript, selects triggers from DE data, or builds one supported
        two-input AND gate from two explicitly chosen DE genes. Arbitrary Boolean
        circuit design is future work.
      </Caveat>
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {WORKFLOWS.map((item) => (
          <Panel key={item.id}>
            <div id={item.id} className="scroll-mt-48 lg:scroll-mt-24">
              <h2 className="text-lg font-semibold text-foreground">
                {item.title}
              </h2>
              <dl className="mt-4 space-y-3 text-sm">
                {[
                  ["Goal", item.goal],
                  ["Required input", item.input],
                  ["Observable output", item.output],
                  ["Limitation", item.limit],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt className="font-mono text-[11px] uppercase tracking-wider text-mint">
                      {label}
                    </dt>
                    <dd className="mt-1 text-muted-foreground">{value}</dd>
                  </div>
                ))}
              </dl>
              <a
                href={item.href}
                className="mt-5 inline-block text-sm font-medium text-mint underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint"
              >
                {item.next} →
              </a>
            </div>
          </Panel>
        ))}
      </div>
      <Panel className="mt-6">
        <div id="not-established" className="scroll-mt-48 lg:scroll-mt-24">
          <h2 className="text-lg font-semibold text-foreground">
            What CERNAL does not establish
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            A ranking is not experimental validation, a success probability, a
            clinical or therapeutic claim, proof of safety, proof of
            specificity, or an orderable complete vector. LocalEngine does not
            perform real off-target scanning; human DE processing, arbitrary A
            AND NOT B logic, multi-gene construction, PDF reports, and partner
            ordering are not complete pipelines.
          </p>
        </div>
      </Panel>
    </>
  );
}
