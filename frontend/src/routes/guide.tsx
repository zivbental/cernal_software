import { createFileRoute } from "@tanstack/react-router";
import { BookOpen } from "lucide-react";
import type { ReactNode } from "react";

import { CodeBlock } from "@/components/docs/CodeBlock";
import { Caveat, HelpLink, HelpNav } from "@/components/docs/HelpNav";
import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Panel } from "@/components/layout/Primitives";

const BASE =
  "https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f";

export const Route = createFileRoute("/guide")({
  component: () => (
    <RequireAuth>
      <AppShell>
        <GuideContent />
      </AppShell>
    </RequireAuth>
  ),
});

const SETUP = `# From the repository root
uv sync --locked --extra dev
cd frontend
npm ci
npm run build:fast
npm run build
cd ..
./do migrate
./do superuser`;

const RUN = `# Terminal 1, from the repository root
./do dev

# Terminal 2, from the repository root
./do worker`;

function GuideSection({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <Panel>
      <div id={id} className="scroll-mt-48 lg:scroll-mt-24">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">
          {title}
        </h2>
        <div className="mt-4 space-y-4 text-sm leading-6 text-muted-foreground">
          {children}
        </div>
      </div>
    </Panel>
  );
}

export function GuideContent() {
  return (
    <>
      <PageHeader
        kicker={
          <>
            <BookOpen className="h-3 w-3" /> Quick Guide
          </>
        }
        title="How to compile a circuit"
        description="A task-first path from a supported input to an inspectable run."
      />
      <HelpNav current="/guide" />
      <nav
        aria-label="On this page"
        className="mb-6 rounded-xl border border-border bg-surface p-4"
      >
        <h2 className="text-sm font-semibold text-foreground">On this page</h2>
        <ol className="mt-2 flex flex-wrap gap-x-5 gap-y-2 text-sm text-mint">
          <li>
            <a href="#before-running">Before running</a>
          </li>
          <li>
            <a href="#local-setup">Local setup</a>
          </li>
          <li>
            <a href="#choose-input">Choose input</a>
          </li>
          <li>
            <a href="#configure">Configure</a>
          </li>
          <li>
            <a href="#payload-vector">Payload and vector</a>
          </li>
          <li>
            <a href="#submit">Submit</a>
          </li>
          <li>
            <a href="#interpret">Interpret</a>
          </li>
          <li>
            <a href="#record">Reproducibility</a>
          </li>
        </ol>
      </nav>
      <div className="space-y-6">
        <GuideSection id="before-running" title="Before running">
          <p>
            An administrator must approve a newly registered account; no
            approval email is sent. Ask the administrator directly, then sign
            in.
          </p>
          <Caveat>
            The only engine is <strong>LocalEngine</strong>, which reports real
            measurements from an incomplete pipeline — never simulated numbers.
            Check{" "}
            <HelpLink href="/api/version">/api/version</HelpLink>:{" "}
            <code>engine_version</code> identifies the build, while capability
            listings show availability—not scientific completeness. A family can
            be listed as available and still refuse to build for want of a
            payload library.
          </Caveat>
          <p>
            See the repository&apos;s{" "}
            <HelpLink href={`${BASE}/docs/development.md`}>
              development setup
            </HelpLink>
            , <HelpLink href={`${BASE}/docs/engine.md`}>engine scope</HelpLink>,
            and the <HelpLink href="/faq#engine-mode">engine-mode FAQ</HelpLink>
            .
          </p>
        </GuideSection>

        <GuideSection id="local-setup" title="Reproducible local setup">
          <p>
            A <code>.env</code> file is optional for local development because
            settings have defaults. Use the repository-pinned Python 3.13,{" "}
            <code>uv</code>, and Node 22+.
          </p>
          <CodeBlock code={SETUP} label="bash" />
          <p>
            Run the web process and worker in separate terminals, then open{" "}
            <HelpLink href="http://localhost:8000">
              http://localhost:8000
            </HelpLink>
            . Without the worker, submitted runs stay queued.
          </p>
          <CodeBlock code={RUN} label="bash" />
        </GuideSection>

        <GuideSection id="choose-input" title="1. Choose the host and input">
          <p>
            <strong>Differential Expression:</strong> choose a public catalog
            comparison or upload an existing DE result, not raw counts. This
            flow does not run differential-expression analysis. LocalEngine supports
            this path for E. coli and yeast, not human; gene identifiers must resolve
            in the bundled reference.
          </p>
          <p>
            <strong>Direct Trigger mRNA:</strong> paste the known transcript
            sequence. This bypasses DE discovery; it does not add the missing
            human promoter, terminator, or complete human pipeline.{" "}
            <strong>Specific Gene</strong> is informational only: you must still
            paste its sequence.
          </p>
          <Caveat>
            Upload validation accepts <code>.csv</code>, <code>.tsv</code>,{" "}
            <code>.txt</code>, and <code>.xlsx</code>, but LocalEngine&apos;s
            real DE parser reads UTF-8 CSV/TSV text only. The default upload
            limit is 100 MB and is configurable with <code>MAX_DATASET_MB</code>
            . A “VALID” upload is shallow file validation.
          </Caveat>
          <p>
            Include a recognized gene identifier and fold-change column.{" "}
            <code>FC</code> and <code>fold_change</code> are treated as
            already-log2 values. Supply <code>log2(target/control)</code> values
            and prefer <code>log2FoldChange</code>.
          </p>
        </GuideSection>

        <GuideSection id="configure" title="2. Validate and configure logic">
          <p>
            Confirm the chosen dataset or transcript. The current LocalEngine
            builds a single-trigger path. The A/B fields illustrate future
            logic; arbitrary A AND NOT B and multi-gene Boolean design are not
            implemented.
          </p>
          <p>
            Choose only mechanisms reported available. Capability availability
            does not imply a complete scientific pipeline.
          </p>
        </GuideSection>

        <GuideSection
          id="payload-vector"
          title="3. Choose a payload and vector"
        >
          <p>
            Select at least one downstream output. Selecting several asks the
            engine for separate output-specific candidates; it does not create
            one fused, multi-output plasmid. “Other” requires a custom coding
            sequence. A displayed output can still be unbuildable for the chosen
            host; inspect warnings or the failure summary rather than assuming every
            UI selection is supported by LocalEngine.
          </p>
          <p>
            Choose a catalog vector, no backbone, or Custom. Custom requires
            GenBank input. Yeast has no bundled catalog backbone, so use a
            custom backbone or accept no backbone. “No backbone” is a bare
            construct, not a promised complete orderable vector. See{" "}
            <HelpLink href="/faq#payload-vector">
              payload and host issues
            </HelpLink>
            .
          </p>
        </GuideSection>

        <GuideSection id="submit" title="4. Submit and observe status">
          <p>
            Submit with <strong>Compile &amp; Optimize</strong>. The
            configuration is frozen and queued. Keep the run URL and watch its
            status; queued work needs <code>./do worker</code>. A failed run
            exposes its safe <code>error_summary</code>.
          </p>
        </GuideSection>

        <GuideSection id="interpret" title="5. Interpret results and downloads">
          <p>
            Scores are weighted rankings, not probabilities of experimental
            success. Missing metrics mean “not measured,” not zero. In Precision
            Filters, enable <strong>Show rejected candidates</strong> to see
            stored rejected rows and their reasons. Trigger windows filtered or
            skipped before candidate creation may instead be summarized in run
            warnings.
          </p>
          <p>
            The results page currently does not render run-level warnings.
            Inspect them in <code>GET /api/runs/{"{run_id}"}</code> through the{" "}
            <HelpLink href="/api-docs">API Reference</HelpLink>, or download{" "}
            <code>manifest.json</code>. Inspect the frozen configuration through{" "}
            <code>GET /api/runs/{"{run_id}"}/detail</code>.
          </p>
          <p>
            Every successfully imported run gets the platform&apos;s per-run
            candidate table <code>summary.csv</code> and{" "}
            <code>manifest.json</code>. LocalEngine additionally emits the per-run{" "}
            <code>candidates.csv</code>, plus FASTA, GenBank and SBOL files for
            accepted switch candidates. Those sequence files appear only once the
            safety screen releases a sequence; with no screening adapter
            provisioned the gate holds every one, leaving the candidate table and
            per-candidate safety audits. ZIP downloads package the existing
            artifacts. The current
            LocalEngine does not generate PDF, structure-figure, or circuit-diagram
            artifacts; the in-app schematic views are separate. Partner ordering
            is disabled.
          </p>
        </GuideSection>

        <GuideSection id="record" title="6. Keep a reproducibility record">
          <p>
            The manifest records parameters, engine version, scoring-profile
            label, seed, warnings, timestamps, candidate count, and the input
            mode plus trigger sequence or dataset name. It is useful provenance,
            but not the whole reproducibility record.
          </p>
          <p>
            Preserve the original DE file, dataset and artifact checksums,
            idempotency key, Git commit, and dependency environment separately.
            Reusing an idempotency key returns the existing run rather than
            recomputing it. The engine is seeded from the run's seed, so a new seed can
            change simulated output even with the same seed. Different engines,
            versions, profiles, or environments need not produce byte-identical
            output. Continue with the{" "}
            <HelpLink href="/faq#reproducibility">reproducibility FAQ</HelpLink>
            .
          </p>
        </GuideSection>
      </div>
    </>
  );
}
