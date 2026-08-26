import { createFileRoute } from "@tanstack/react-router";
import { Lightbulb } from "lucide-react";

import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Panel } from "@/components/layout/Primitives";

export const Route = createFileRoute("/use-cases")({
  component: () => (
    <RequireAuth>
      <AppShell>
        <UseCasesPage />
      </AppShell>
    </RequireAuth>
  ),
});

/**
 * Placeholder content.
 *
 * The Lovable export listed "Use Cases" in the navigation but shipped no content for it,
 * so these are illustrative rather than authored (docs/architecture.md §8).
 */
const CASES = [
  {
    title: "Inflammation-gated reporter",
    body: "Fire only where inflammatory transcripts are elevated and regulatory markers are absent, so the readout tracks disease state rather than cell count.",
  },
  {
    title: "Stress-response biosensor",
    body: "Detect the transition from normal metabolism to oxidative stress in a bacterial culture, and report it fluorescently.",
  },
  {
    title: "Selective kill-switch",
    body: "Couple a two-input AND gate to an apoptosis inducer so that only cells matching both conditions are removed.",
  },
];

function UseCasesPage() {
  return (
    <>
      <PageHeader
        kicker={
          <>
            <Lightbulb className="h-3 w-3" /> Use Cases
          </>
        }
        title="What people build with CERNAL"
        description="Illustrative circuits, to show the shape of problems CERNAL is designed for."
      />

      <div className="mb-6 rounded-xl border border-dashed border-border bg-surface p-4 text-sm text-muted-foreground">
        These examples are placeholders. Replace them with real circuits from the team
        once the wet lab has results to point at.
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {CASES.map((item) => (
          <Panel key={item.title}>
            <h2 className="text-base font-semibold text-foreground">{item.title}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{item.body}</p>
          </Panel>
        ))}
      </div>
    </>
  );
}
