import { createFileRoute } from "@tanstack/react-router";
import { CircleHelp } from "lucide-react";
import type { ReactNode } from "react";

import { HelpLink } from "@/components/docs/HelpNav";
import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Panel } from "@/components/layout/Primitives";

const BASE =
  "https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f";

export const Route = createFileRoute("/faq")({
  component: () => (
    <RequireAuth>
      <AppShell>
        <FaqContent />
      </AppShell>
    </RequireAuth>
  ),
});

type FaqItem = { id: string; question: string; answer: ReactNode };
type FaqGroup = { id: string; title: string; items: FaqItem[] };

const GROUPS: FaqGroup[] = [
  {
    id: "setup-access",
    title: "Setup and access",
    items: [
      {
        id: "pending-approval",
        question: "Why can’t I sign in after registering?",
        answer: (
          <>
            Accounts begin inactive until a staff administrator approves them.
            No approval email is sent, so contact the administrator directly.
            See <HelpLink href="/guide#before-running">Before running</HelpLink>
            .
          </>
        ),
      },
      {
        id: "queued-worker",
        question: "Why is my run still queued?",
        answer: (
          <>
            A worker must be running. <code>./do dev</code> starts and supervises
            it automatically. If the worker is offline, the run screen says so;
            your submission stays saved until it reconnects. See{" "}
            <HelpLink href="/guide#local-setup">local setup</HelpLink>.
          </>
        ),
      },
      {
        id: "engine-mode",
        question: "Which engine am I running?",
        answer: (
          <>
            Check <HelpLink href="/api/version">/api/version</HelpLink>. There
            is only one engine: <code>LocalEngine</code>, the real pipeline, and
            it is the default. The simulated MockEngine was removed — the product
            reports real measurements or it reports a failure, never fabricated
            numbers. Set{" "}
            <code>CERNAL_ENGINE=engine.client.LocalEngine</code> for both the web
            and worker processes. A local <code>.env</code> is optional because
            defaults exist. See{" "}
            <HelpLink href={`${BASE}/.env.example`}>.env.example</HelpLink> and{" "}
            <HelpLink href={`${BASE}/docs/development.md`}>
              setup documentation
            </HelpLink>
            .
          </>
        ),
      },
      {
        id: "upload-limit",
        question: "How large can an upload be?",
        answer: (
          <>
            The default dataset limit is 100 MB. Operators can change{" "}
            <code>MAX_DATASET_MB</code>; users cannot override it per upload.
            See{" "}
            <HelpLink href="/guide#choose-input">input preparation</HelpLink>.
          </>
        ),
      },
    ],
  },
  {
    id: "inputs-workflows",
    title: "Inputs and supported workflows",
    items: [
      {
        id: "upload-parsing",
        question: "Why can a valid upload fail when the engine runs?",
        answer: (
          <>
            Upload validation is shallow and accepts .csv, .tsv, .txt, and
            .xlsx. LocalEngine reads UTF-8 CSV/TSV text, requires a recognized
            gene identifier and usable fold-change value, and can reject or drop
            rows later.
          </>
        ),
      },
      {
        id: "fold-change",
        question: "What does FC or fold_change mean?",
        answer: (
          <>
            Those aliases are consumed as log2 fold change and are not
            transformed. Provide log2(target/control) values;{" "}
            <code>log2FoldChange</code> is the clearest header.
          </>
        ),
      },
      {
        id: "gene-picker",
        question: "Does Specific Gene fetch a transcript sequence?",
        answer: (
          <>
            No. It records the selection for context, then requires you to paste
            the exact sequence through Direct Trigger mRNA.
          </>
        ),
      },
      {
        id: "host-scope",
        question: "Which hosts does LocalEngine support?",
        answer: (
          <>
            Direct, DE, and Specific Gene input are supported for E. coli, yeast,
            C. acnes, and Human. Human constructs use a CMV promoter and
            hGH polyadenylation signal with a custom mammalian backbone or no
            backbone. Human discovery uses mature transcripts from Ensembl release 116.
          </>
        ),
      },
      {
        id: "families",
        question:
          "Does an available gate family mean the whole pipeline is complete?",
        answer: (
          <>
            No. Availability is a capability flag, not proof of scientific
            completeness. Follow the run warnings and current engine/version
            scope.
          </>
        ),
      },
      {
        id: "boolean-logic",
        question: "Can LocalEngine compile arbitrary A AND NOT B logic?",
        answer: (
          <>
            No. The current real path is single-trigger/single-gene. Multi-gene
            Boolean design remains future work. See{" "}
            <HelpLink href="/guide#configure">configure logic</HelpLink>.
          </>
        ),
      },
      {
        id: "payload-vector",
        question: "How do payload and vector choices work?",
        answer: (
          <>
            Choose at least one output. “Other” needs a custom coding sequence,
            and a Custom vector needs GenBank input. Multiple outputs create
            separate output-specific candidates, not a fused plasmid. Yeast has
            no bundled catalog backbone. See{" "}
            <HelpLink href="/guide#payload-vector">
              the payload/vector step
            </HelpLink>
            .
          </>
        ),
      },
    ],
  },
  {
    id: "results-limitations",
    title: "Results and limitations",
    items: [
      {
        id: "scores",
        question: "Is a score a probability of success?",
        answer: (
          <>
            No. It is a weighted ranking under a scoring profile. It does not
            establish experimental success, safety, specificity, or therapeutic
            suitability.
          </>
        ),
      },
      {
        id: "missing-metrics",
        question: "Does a missing metric mean zero?",
        answer: (
          <>
            No. Missing means it was not measured or could not be computed, not
            that its raw value was zero. The scoring profile controls the penalty;
            the default missing-value policy treats it as worst at full weight.
          </>
        ),
      },
      {
        id: "off-targets",
        question: "Does CERNAL perform real off-target scanning?",
        answer: (
          <>
            No. LocalEngine currently uses placeholder off-target values and
            warnings; it does not run a real transcriptome matcher.
          </>
        ),
      },
      {
        id: "missing-candidates",
        question: "Why are candidates absent?",
        answer: (
          <>
            Precision Filters may hide stored rejected or low-scoring rows.
            Enable <strong>Show rejected candidates</strong> to inspect stored
            rejection reasons. Trigger windows filtered or skipped earlier may
            only be summarized in warnings, rather than becoming one rejected
            row each.
          </>
        ),
      },
      {
        id: "warnings",
        question: "Where are warnings and the frozen configuration?",
        answer: (
          <>
            The run page does not currently render run-level warnings. Use the{" "}
            <HelpLink href="/api-docs">API Reference</HelpLink>:{" "}
            <code>GET /api/runs/{"{run_id}"}</code> returns warnings, and{" "}
            <code>GET /api/runs/{"{run_id}"}/detail</code> returns the frozen
            configuration. Warnings are also in <code>manifest.json</code>.
          </>
        ),
      },
      {
        id: "failed-run",
        question: "Where do I find the cause of a failed run?",
        answer: (
          <>
            The run response and page expose a safe <code>error_summary</code>.
            Report that summary and run ID—not secrets or sensitive inputs.
          </>
        ),
      },
      {
        id: "downloads",
        question: "What does a successful run provide?",
        answer: (
          <>
            The platform creates the per-run candidate table{" "}
            <code>summary.csv</code> and <code>manifest.json</code>. LocalEngine
            additionally emits <code>candidates.csv</code> and, once the safety
            screen releases a sequence, accepted-candidate FASTA, GenBank and SBOL
            files. With no screening adapter provisioned the release gate holds every
            sequence, so a run yields the candidate table and per-candidate safety
            audits only. ZIP downloads bundle stored artifacts. PDF, structure-figure,
            and circuit-diagram downloads are not generated by LocalEngine; the
            in-app schematic views are separate.
          </>
        ),
      },
      {
        id: "sharing",
        question: "Can I share a run by sending its URL?",
        answer: (
          <>
            Run URLs are owner-scoped, with authorized staff access. Sharing a
            URL does not grant another user permission to view the run.
          </>
        ),
      },
    ],
  },
  {
    id: "reproducibility",
    title: "Reproducibility and contributing",
    items: [
      {
        id: "repeatability",
        question: "What does manifest.json preserve?",
        answer: (
          <>
            It records parameters, engine version, scoring-profile label, seed,
            warnings, timestamps, candidate count, and input mode plus trigger
            sequence or dataset name. Separately preserve the original DE file,
            dataset/artifact checksums, idempotency key, Git commit, and
            dependency environment. Reusing an idempotency key returns the
            existing run, not a fresh computation. See{" "}
            <HelpLink href="/guide#record">
              the reproducibility checklist
            </HelpLink>
            .
          </>
        ),
      },
      {
        id: "contributing",
        question: "How should I contribute a fix?",
        answer: (
          <>
            Create a focused branch, update tests, run the documented checks,
            and open a pull request. Start with{" "}
            <HelpLink href={`${BASE}/docs/development.md`}>
              development.md
            </HelpLink>
            , <HelpLink href={`${BASE}/docs/engine.md`}>engine.md</HelpLink>,
            and{" "}
            <HelpLink href={`${BASE}/frontend/src/routes/compile.tsx`}>
              the compiler source
            </HelpLink>
            . Source code wins when historical prose disagrees.
          </>
        ),
      },
      {
        id: "security-privacy",
        question: "What belongs in a bug report?",
        answer: (
          <>
            Include reproducible steps, safe error text, versions, and
            non-sensitive fixtures. Remove secrets, personal information,
            unpublished sequences, and sensitive datasets.
          </>
        ),
      },
    ],
  },
];

export function FaqContent() {
  return (
    <>
      <PageHeader
        kicker={
          <>
            <CircleHelp className="h-3 w-3" /> FAQ
          </>
        }
        title="Frequently asked questions"
        description="Direct answers about setup, supported inputs, results, and repeatability."
      />
      <nav
        aria-label="FAQ topics"
        className="mb-6 flex flex-wrap gap-3 text-sm text-mint"
      >
        {GROUPS.map((group) => (
          <a key={group.id} href={`#${group.id}`}>
            {group.title}
          </a>
        ))}
      </nav>
      <div className="space-y-6">
        {GROUPS.map((group) => (
          <Panel key={group.id}>
            <section
              id={group.id}
              className="scroll-mt-48 lg:scroll-mt-24"
              aria-labelledby={`${group.id}-heading`}
            >
              <h2
                id={`${group.id}-heading`}
                className="text-xl font-semibold text-foreground"
              >
                {group.title}
              </h2>
              <div className="mt-5 space-y-6">
                {group.items.map((item) => (
                  <article key={item.id} id={item.id} className="scroll-mt-48 lg:scroll-mt-24">
                    <h3 className="text-base font-semibold text-foreground">
                      {item.question}
                    </h3>
                    <div className="mt-1 text-sm leading-6 text-muted-foreground">
                      {item.answer}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </Panel>
        ))}
      </div>
    </>
  );
}
