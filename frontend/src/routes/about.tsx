import { createFileRoute } from "@tanstack/react-router";
import { Users } from "lucide-react";

import cernalLogo from "@/assets/cernal-logo-animated.svg";
import { useVersion } from "@/api/queries";
import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Panel } from "@/components/layout/Primitives";

export const Route = createFileRoute("/about")({
  component: () => (
    <RequireAuth>
      <AppShell>
        <AboutPage />
      </AppShell>
    </RequireAuth>
  ),
});

function AboutPage() {
  const { data: version } = useVersion();

  return (
    <>
      <PageHeader
        kicker={
          <>
            <Users className="h-3 w-3" /> About Us
          </>
        }
        title="CERNAL"
        description="Compiler-like Engine for RNA Logic — TAU iGEM."
      />

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Panel>
          <img src={cernalLogo} alt="CERNAL" className="h-12 w-auto" />
          <p className="mt-6 text-sm leading-relaxed text-muted-foreground">
            CERNAL turns transcriptomic signals into manufacturable synthetic gene
            circuits. Researchers define activation conditions as constraints; CERNAL
            returns an optimized genetic blueprint with a high signal-to-noise ratio.
          </p>
          <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
            The core idea is that RNA-based switches — toehold switches, CRISPR guide RNAs
            — follow universal thermodynamics regardless of host organism. Circuits built
            this way are organism-agnostic: the same design principles hold in E. coli,
            yeast and mammalian cells.
          </p>
          <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
            Built by a multidisciplinary student team at Tel Aviv University spanning dry
            lab, wet lab and human practices.
          </p>
          <a
            href="https://2025.igem.wiki/tau-israel"
            target="_blank"
            rel="noreferrer"
            className="mt-6 inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm text-foreground hover:border-mint"
          >
            Full project documentation on the iGEM wiki
          </a>
        </Panel>

        <Panel>
          <h2 className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            System
          </h2>
          <dl className="mt-4 space-y-3 font-mono text-xs">
            {[
              ["Application", version ? `v${version.app_version}` : "—"],
              ["API schema", version?.api_schema_version ?? "—"],
              ["Engine", version?.engine ?? "—"],
              ["Engine version", version?.engine_version ?? "—"],
              [
                "Mechanisms",
                version?.gate_families
                  .map((f) => `${f.name}${f.available ? "" : " (planned)"}`)
                  .join(", ") ?? "—",
              ],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4 border-b border-border pb-2">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="text-right text-foreground">{value}</dd>
              </div>
            ))}
          </dl>

          {version?.engine === "MockEngine" && (
            <p className="mt-5 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-muted-foreground">
              This deployment runs the <strong className="text-foreground">mock engine</strong>.
              Candidates are structurally realistic but the numbers are simulated — they are
              not scientific predictions.
            </p>
          )}
        </Panel>
      </div>
    </>
  );
}
