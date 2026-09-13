import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { BookMarked, Download, KeyRound, ShieldCheck, Sparkles, Terminal } from "lucide-react";
import type { ReactNode } from "react";

import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Panel, SectionHeading } from "@/components/layout/Primitives";
import { CodeBlock } from "@/components/docs/CodeBlock";
import { DocsSidebar } from "@/components/docs/DocsSidebar";
import { MetricsChart, METRICS } from "@/components/docs/MetricsChart";
import { ObjectMap, RequestFlow } from "@/components/docs/Diagrams";
import { ClientReferenceView } from "@/components/docs/ClientReference";
import { ParamTable, type ParamRow } from "@/components/docs/ParamTable";

export const Route = createFileRoute("/api-docs")({
  component: () => (
    <RequireAuth>
      <AppShell>
        <ApiDocsPage />
      </AppShell>
    </RequireAuth>
  ),
});

/**
 * One entry per client. Every snippet submits the same request — a trigger sequence
 * against E. coli — so the four tabs read as translations of each other, not four
 * unrelated examples. Mirrors docs/public-api.md §8-§11 and clients/{python,r,matlab}/.
 */
const LANGUAGES = [
  {
    id: "python",
    label: "Python",
    install: "pip install cernal\n# or: pip install cernal[pandas]",
    authenticate: `import os
from cernal import Client

c = Client(api_key=os.environ["CERNAL_API_KEY"], base_url="https://your-cernal-host")`,
    quick: `job = c.design(trigger_sequence="AUGGCUAAGCUUAACGGAUCC", organism="ecoli")
df = job.wait().to_dataframe()
print(df.head())`,
    full: `job = c.design(
    dge_csv=open("deseq2.csv").read(),
    organism="ecoli",
    gate_families=["toehold"],
    constraints={
        "max_triggers": 2, "min_separation": 1.0, "max_p_adj": 0.01,
        "trigger_lengths": [30, 36], "standard": "RFC10",
    },
    scoring={
        "weights": {"predicted_leakage": 4.0, "gc_content": 0.0},
        "hard_filters": [{"metric": "dynamic_range", "minimum": 10.0}],
    },
    budget={"max_designs": 50_000, "max_runtime_seconds": 1800},
    seed=42,
    top_n=25,
)
print(job.estimate)          # from the 202, before waiting
best = job.wait().best()     # highest-ranked candidate, as a dict
job.artifact("fasta").save("best.fa")`,
    polling: `# block up to 60s for the finished result, inline
job = c.design(trigger_sequence="AUGGCUAAGCUUAACGGAUCC", organism="ecoli", wait=60)

# cost a whole sweep before running any of it — see the Recipes below
cheap = Client(api_key=os.environ["CERNAL_API_KEY"], base_url="https://your-cernal-host",
               dry_run=True)
print(cheap.design(trigger_sequence=seq, organism="ecoli").estimate)`,
    errors: `from cernal import AuthError, ValidationError, RateLimited, RunFailed

try:
    job = c.design(trigger_sequence=seq, organism="ecoli").wait()
except ValidationError as e:
    print(e.message, "— did you mean:", e.did_you_mean)
except RateLimited as e:
    print("retry after", e.retry_after, "seconds")
except RunFailed as e:
    print(e.error_summary)
except AuthError as e:
    print("bad key:", e)`,
  },
  {
    id: "r",
    label: "R",
    install: 'remotes::install_github("zivbental/cernal_software", subdir = "clients/r")',
    authenticate: `library(cernal)
cl <- cernal_client(Sys.getenv("CERNAL_API_KEY"), base_url = "https://your-cernal-host")`,
    quick: `job <- cernal_design(cl, trigger_sequence = "AUGGCUAAGCUUAACGGAUCC", organism = "ecoli")
df  <- cernal_results(cernal_wait(job))
head(df)`,
    full: `job <- cernal_design(
  cl,
  dge_csv       = readr::read_file("deseq2.csv"),
  organism      = "ecoli",
  gate_families = "toehold",
  constraints   = list(max_triggers = 2L, min_separation = 1.0, max_p_adj = 0.01,
                       trigger_lengths = c(30L, 36L), standard = "RFC10"),
  scoring       = list(weights = list(predicted_leakage = 4.0, gc_content = 0.0),
                       hard_filters = list(list(metric = "dynamic_range", minimum = 10.0))),
  budget        = list(max_designs = 50000L, max_runtime_seconds = 1800L),
  seed = 42L, top_n = 25L
)
df   <- cernal_results(cernal_wait(job))
best <- cernal_best(job)
cernal_artifact(job, "fasta", "best.fa")`,
    polling: `# block up to 60s for the finished result, inline
job <- cernal_design(cl, trigger_sequence = "AUGGCUAAGCUUAACGGAUCC",
                      organism = "ecoli", wait = 60)

# the flagship demo — see "DESeq2 → plasmid design" in the Recipes below
deseq_table <- as.data.frame(DESeq2::results(dds))
job <- cernal_design(cl, dge_csv = readr::format_csv(deseq_table), organism = "ecoli")`,
    errors: `result <- tryCatch(
  cernal_results(cernal_wait(cernal_design(cl, trigger_sequence = seq, organism = "ecoli"))),
  cernal_validation_error = function(e) { message(e$detail$did_you_mean); NULL },
  cernal_rate_limited     = function(e) { message("retry after ", e$retry_after); NULL },
  cernal_run_failed       = function(e) { message(e$error_summary); NULL },
  cernal_auth_error       = function(e) { message("bad key: ", e$message); NULL }
)`,
  },
  {
    id: "matlab",
    label: "MATLAB",
    install: "addpath('/path/to/cernal_software/clients/matlab');",
    authenticate:
      "c = cernal.Client(getenv('CERNAL_API_KEY'), 'BaseURL', 'https://your-cernal-host');",
    quick: `job = c.design('trigger_sequence', 'AUGGCUAAGCUUAACGGAUCC', 'organism', 'ecoli');
T = job.wait().results();
head(T)`,
    full: `job = c.design('dge_csv', fileread('deseq2.csv'), ...
               'organism', 'ecoli', ...
               'gate_families', {'toehold'}, ...
               'constraints', struct('max_triggers', 2, 'min_separation', 1.0, ...
                                      'max_p_adj', 0.01, 'standard', 'RFC10'), ...
               'scoring', struct('weights', struct('predicted_leakage', 4.0, ...
                                                     'gc_content', 0.0)), ...
               'budget', struct('max_designs', 50000, 'max_runtime_seconds', 1800), ...
               'seed', 42, 'top_n', 25);
T = job.wait().results();
writetable(T, 'candidates.csv');
job.artifact('fasta', 'best.fa');`,
    polling: `% block up to 60s for the finished result, inline
job = c.design('trigger_sequence', 'AUGGCUAAGCUUAACGGAUCC', 'organism', 'ecoli', 'wait', 60);`,
    errors: `try
    job = c.design('trigger_sequence', seq, 'organism', 'ecoli').wait();
catch err
    switch err.identifier
        case 'cernal:ValidationError'
            disp(err.message)
        case 'cernal:RateLimited'
            disp(err.message)
        case 'cernal:AuthError'
            disp(err.message)
        otherwise
            rethrow(err)
    end
end`,
  },
  {
    id: "curl",
    label: "curl",
    install: undefined,
    authenticate: `KEY=cern_live_7Kd2mQ8vF3xR9wLbN4pT6yH1sJ0aZcVe
HOST=https://your-cernal-host`,
    quick: `curl -s "$HOST/api/design?wait=60" \\
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \\
  -d '{"trigger_sequence": "AUGGCUAAGCUUAACGGAUCC", "organism": "ecoli"}'`,
    full: `curl -s "$HOST/api/design" -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{
  "dataset_id": "…",
  "organism": "ecoli",
  "gate_families": ["toehold"],
  "constraints": {"max_triggers": 2, "min_separation": 1.0, "max_p_adj": 0.01,
                   "trigger_lengths": [30, 36], "standard": "RFC10"},
  "scoring": {"weights": {"predicted_leakage": 4.0, "gc_content": 0.0},
              "hard_filters": [{"metric": "dynamic_range", "minimum": 10.0}]},
  "budget": {"max_designs": 50000, "max_runtime_seconds": 1800},
  "seed": 42, "top_n": 25
}'`,
    polling: `JOB=$(curl -s "$HOST/api/design" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \\
  -d '{"trigger_sequence": "AUGGCUAAGCUUAACGGAUCC", "organism": "ecoli"}' | jq -r .job_id)

curl -s "$HOST/api/design/$JOB" -H "X-API-Key: $KEY"
curl -s "$HOST/api/design/$JOB/results?top_n=10" -H "X-API-Key: $KEY" | jq '.candidates[0]'
curl -s "$HOST/api/design/$JOB/results?format=csv" -H "X-API-Key: $KEY" -o candidates.csv`,
    errors: `# every failure has one shape, whatever the language:
{"error": {"code": "unknown_parameter",
           "message": "Unknown constraint 'max_trigger'.",
           "detail": {"did_you_mean": "max_triggers", "allowed": ["max_triggers", …]}}}`,
  },
] as const;

const PARAMETERS: ParamRow[] = [
  { field: "trigger_sequence", type: "string", default: '""', notes: "Direct mode: the mRNA, pasted. Exactly one of these three input fields." },
  { field: "dataset_id", type: "uuid", default: "null", notes: "DE mode: an existing, VALID dataset you own." },
  { field: "dge_csv", type: "string", default: '""', notes: "DE mode: an inline differential-expression table — creates a dataset." },
  { field: "organism", type: "string", default: '""', notes: "e.g. \"E. coli\". Stored on the run." },
  { field: "gate_families", type: "string[] | null", default: "null (all available)", notes: "Which switch chemistries may be used." },
  { field: "exclude_gate_families", type: "string[]", default: "[]", notes: "Alternative phrasing: allow every available family except these." },
  { field: "constraints", type: "object", default: "{}", notes: "Search constraints — every field explained in the table below." },
  { field: "scoring", type: "object", default: "{}", notes: "Re-weight the nine metrics for this run — every field explained below." },
  { field: "budget", type: "object", default: "{}", notes: "Cost ceiling for this run — every field explained below." },
  { field: "payload", type: "object", default: "{}", notes: "What the circuit expresses — every field explained below." },
  { field: "top_n", type: "integer", default: "25", notes: "How many ranked candidates the results endpoint returns." },
  { field: "include_rejected", type: "boolean", default: "false", notes: "Include candidates a hard filter disqualified, with their reason." },
  { field: "include_metrics", type: "boolean", default: "true", notes: "Embed the full metric decomposition per candidate." },
  { field: "include_artifacts", type: "string[]", default: "[]", notes: 'Artifact kinds to embed, e.g. ["fasta", "structure_svg"].' },
  { field: "seed", type: "integer | null", default: "null", notes: "Reproducibility — same seed and inputs, same candidates." },
  { field: "idempotency_key", type: "string | null", default: "null", notes: "Resubmitting with the same key returns the existing run." },
  { field: "strict", type: "boolean", default: "true", notes: "An unknown key in constraints/scoring/budget/payload is a 422 with did_you_mean." },
  { field: "notes", type: "string", default: '""', notes: "Free text, echoed back — not read by the engine." },
];

const CONSTRAINTS_FIELDS: ParamRow[] = [
  { field: "max_triggers", type: "integer", default: "2", notes: "Circuit arity ceiling — how many triggers a circuit may combine." },
  { field: "min_separation", type: "float", default: "0.5", notes: "Minimum |log2 fold change| for a gene to be considered usable." },
  { field: "max_p_adj", type: "float", default: "0.05", notes: "Adjusted p-value significance threshold." },
  { field: "trigger_lengths", type: "integer[]", default: "[30, 36]", notes: "Window sizes to scan, in nt." },
  { field: "max_switch_length", type: "integer", default: "200", notes: "Synthesis length ceiling, in nt." },
  { field: "forbidden_motifs", type: "string[]", default: "[]", notes: 'Sequence motifs to reject, e.g. ["GGTCTC", "GAATTC"].' },
  { field: "standard", type: "string", default: '"RFC10"', notes: '"RFC10" | "RFC1000" — which restriction sites are banned.' },
];

const SCORING_FIELDS: ParamRow[] = [
  { field: "base", type: "string", default: '"default"', notes: "Which named scoring profile to start from." },
  { field: "weights", type: "object", default: "{}", notes: "metric_name → weight. Only the nine DEFAULT_V1 names are accepted — see Scoring below." },
  { field: "hard_filters", type: "array", default: "[]", notes: "[{metric, minimum, maximum, reason}] — merged with the base profile's own two, not a replacement." },
  { field: "tie_breakers", type: "string[]", default: "base profile's", notes: "Metric names in order. Replaces the base list outright when given." },
];

const BUDGET_FIELDS: ParamRow[] = [
  { field: "max_designs", type: "integer", default: "100,000", notes: "Hard ceiling on designs evaluated for this run." },
  { field: "max_runtime_seconds", type: "integer | null", default: "null", notes: "Hard ceiling on wall-clock runtime for this run." },
  { field: "on_exceed", type: "string", default: '"return_best"', notes: '"return_best" | "fail" — what happens when a ceiling is hit mid-run.' },
];

const PAYLOAD_FIELDS: ParamRow[] = [
  { field: "outputs", type: "string[]", default: "[]", notes: 'What the circuit expresses, e.g. ["gfp", "ampr"].' },
  { field: "custom_sequence", type: "string | null", default: "null", notes: "A custom payload sequence, in place of a named output." },
];

const QUERY_PARAMS = [
  { field: "?wait=<seconds>", notes: "Block server-side for a finished result (ceiling 300s). Falls back to 202 on timeout." },
  { field: "?dry_run=true", notes: "Estimate designs and runtime without submitting — makes no database writes at all." },
];

const SCOPES = [
  { scope: "read", grants: "Every GET — runs, datasets, candidates, artifacts, exports.", forUse: "Dashboards, a shared analysis notebook, CI that checks results." },
  { scope: "design", grants: "POST /api/design, run submission, cancellation, annotations. Implies read.", forUse: "Anything that consumes compute." },
];

const ERROR_CODES = [
  { status: "401", code: "invalid_api_key", when: "Missing, malformed, unknown, revoked or expired — one message for all four, deliberately." },
  { status: "403", code: "insufficient_scope", when: "A read-scoped key attempted POST /api/design." },
  { status: "422", code: "unknown_parameter", when: "strict mode (the default) rejected an unrecognized field, with did_you_mean." },
  { status: "422", code: "validation_failed", when: "A field's value failed validation — e.g. two input modes supplied at once." },
  { status: "429", code: "rate_limited · too_many_active_runs", when: "Over the per-key rate or concurrency ceiling. Carries Retry-After." },
];

const REST_ENDPOINTS = [
  { method: "POST", path: "/api/design", purpose: "Submit. ?wait= optional. ?dry_run=true estimates without running." },
  { method: "GET", path: "/api/design/{id}", purpose: "Status. A thin alias of the existing polling endpoint." },
  { method: "GET", path: "/api/design/{id}/results", purpose: "Ranked candidates with metric decomposition. ?format=json|csv." },
  { method: "GET", path: "/api/artifacts/{id}/download", purpose: "Download one artifact by id." },
  { method: "GET", path: "/api/version", purpose: "Capabilities: gate families, profiles, metrics, units. No key needed." },
];

const SCORING_RULES = [
  { rule: "Only the nine names in DEFAULT_V1 are accepted.", why: "An unknown name (e.g. leakage instead of predicted_leakage) is a triple silent failure server-side — the API turns that silence into a 422 listing all nine instead." },
  { rule: "weights, hard_filters and tie_breakers are overridable. direction and valid_range are not.", why: "Direction and range are physics and units, not preference — widening them would let a run make its own numbers look better and break comparability with everyone else's." },
  { rule: "The derived profile gets a deterministic label: custom-<hash8>.", why: "Two runs with identical weights get the same label, recorded in resolved and on every candidate — so a score stays interpretable after the fact." },
  { rule: "The engine builds the profile, not the API.", why: "The API only validates metric names against GET /api/version; engine.scoring.profiles constructs and validates the actual ScoringProfile." },
];

const SWEEP_RECIPE = `import os
from cernal import Client

# dry_run=True means every call below estimates — nothing is queued, nothing costs compute
cheap = Client(api_key=os.environ["CERNAL_API_KEY"],
               base_url="https://your-cernal-host", dry_run=True)

for organism in ("ecoli", "yeast", "bsubtilis"):
    estimate = cheap.design(trigger_sequence=seq, organism=organism).estimate
    print(f"{organism}: {estimate['designs']} designs, ~{estimate['seconds']}s ({estimate['confidence']})")

# happy with the numbers? the same call against a real client queues it for real
c = Client(api_key=os.environ["CERNAL_API_KEY"], base_url="https://your-cernal-host")
job = c.design(trigger_sequence=seq, organism="ecoli").wait()`;

const SCORING_RECIPE = `job = c.design(
    trigger_sequence=seq,
    organism="ecoli",
    scoring={
        # ignore GC entirely — weight 0.0 keeps it measured and visible, just not ranked on
        "weights": {"predicted_leakage": 4.0, "gc_content": 0.0},
        # an extra disqualifying threshold, merged with the base profile's own two
        "hard_filters": [{"metric": "dynamic_range", "minimum": 10.0}],
        "tie_breakers": ["dynamic_range", "predicted_leakage"],
    },
)
results = job.wait()
best = results.best()
print(best["gate_family"], best["overall_score"])

# two runs with identical weights get the same label, so they stay comparable
print(results.resolved["scoring_profile"])   # "custom-<8-char hash>"`;

const DESEQ2_RECIPE = `library(cernal)

cl <- cernal_client(Sys.getenv("CERNAL_API_KEY"), base_url = "https://your-cernal-host")

# DESeq2::results() straight to plasmid design — no CSV round trip
deseq_table <- as.data.frame(DESeq2::results(dds))

job <- cernal_design(
  cl,
  dge_csv       = readr::format_csv(deseq_table),
  organism      = "ecoli",
  gate_families = "toehold",
  constraints   = list(max_triggers = 2L, min_separation = 1.0, max_p_adj = 0.01),
  scoring       = list(weights = list(predicted_leakage = 4.0)),
  seed          = 42L
)
df <- cernal_results(cernal_wait(job))
head(df)`;

const NOTEBOOK_URL = `${import.meta.env.BASE_URL}downloads/cernal-quickstart.ipynb`;

/** One section: an anchor target for the sidebar, plus the heading it jumps to. */
function Section({
  id,
  kicker,
  title,
  desc,
  children,
}: {
  id: string;
  kicker: string;
  title: string;
  desc: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-32 space-y-6">
      <SectionHeading kicker={kicker} title={title} desc={desc} />
      {children}
    </section>
  );
}

function FeatureCard({ icon, title, desc }: { icon: ReactNode; title: string; desc: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border bg-surface p-4">
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-mint/10 text-mint">
        {icon}
      </div>
      <div>
        <div className="text-sm font-medium text-foreground">{title}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">{desc}</div>
      </div>
    </div>
  );
}

function StatTile({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="font-mono text-xl font-semibold text-foreground">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function ApiDocsPage() {
  const [active, setActive] = useState<(typeof LANGUAGES)[number]["id"]>("python");
  const lang = LANGUAGES.find((l) => l.id === active) ?? LANGUAGES[0];

  return (
    <>
      <PageHeader
        kicker={
          <>
            <BookMarked className="h-3 w-3" /> Developer
          </>
        }
        title="API Reference"
        description="Everything a script needs to submit a design, wait for it, and read the results — in Python, R, MATLAB, or curl. One call in, ranked circuits out."
        actions={
          <Link
            to="/settings"
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm text-foreground hover:border-mint"
          >
            <KeyRound className="h-4 w-4" /> Manage API keys
          </Link>
        }
      />

      {/* Global language switcher — every code sample below (except the fixed Recipes) follows it. */}
      <div className="sticky top-16 z-30 mb-8 flex items-center gap-1 rounded-xl border border-border bg-background/90 p-1 shadow-clinical backdrop-blur-xl">
        {LANGUAGES.map((l) => (
          <button
            key={l.id}
            onClick={() => setActive(l.id)}
            className={`flex-1 rounded-lg px-4 py-2 text-sm transition ${
              active === l.id
                ? "bg-card font-medium text-foreground shadow-clinical"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {l.label}
          </button>
        ))}
      </div>

      <div className="grid gap-10 lg:grid-cols-[224px_1fr]">
        <DocsSidebar />

        <div className="min-w-0 space-y-16">
          <Section
            id="overview"
            kicker="Overview"
            title="A ranked design, in four lines"
            desc="A trigger sequence — or a differential-expression table — goes in. Ranked, scored RNA logic circuit designs come out. Everything below is one REST surface: the SPA, the CLI clients and curl all call the same endpoints."
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <FeatureCard
                icon={<KeyRound className="h-4 w-4" />}
                title="One header to authenticate"
                desc="An X-API-Key header, no cookie jar, no CSRF dance — works from a script, a notebook or Snakemake."
              />
              <FeatureCard
                icon={<Sparkles className="h-4 w-4" />}
                title="One call for the whole pipeline"
                desc="POST /api/design resolves a scoring profile and every default — then queues, or blocks with wait=."
              />
              <FeatureCard
                icon={<ShieldCheck className="h-4 w-4" />}
                title="Same account, same data"
                desc="A run submitted by a script appears in the web UI, owned by you — no separate 'API results' silo."
              />
            </div>
          </Section>

          <Section
            id="authentication"
            kicker="Step 1 · Authenticate"
            title="Hold a key"
            desc="Mint one from the API Keys page — it authenticates every call below, in place of a login. Two scopes cover the two real risk levels."
          >
            <Panel>
              <CodeBlock code={lang.authenticate} label={lang.id} />
            </Panel>
            <div className="overflow-hidden rounded-xl border border-border">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border bg-surface text-[11px] uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3 font-mono">Scope</th>
                    <th className="px-4 py-3">Grants</th>
                    <th className="px-4 py-3">For</th>
                  </tr>
                </thead>
                <tbody>
                  {SCOPES.map((s) => (
                    <tr key={s.scope} className="border-b border-border bg-card last:border-b-0">
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-foreground">
                        {s.scope}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{s.grants}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{s.forUse}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section
            id="quickstart"
            kicker="Step 2 · Submit"
            title="A ranked design, in one call"
            desc="Install the client, then a trigger sequence goes in and ranked candidates, best first, come out."
          >
            {lang.install && (
              <Panel>
                <div className="mb-3 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                  Install
                </div>
                <CodeBlock code={lang.install} label="shell" />
              </Panel>
            )}
            <Panel>
              <CodeBlock code={lang.quick} label={lang.id} />
            </Panel>
          </Section>

          <Section
            id="lifecycle"
            kicker="How it works"
            title="Request lifecycle"
            desc="A design either queues and you poll (or hand it to wait=), or you cost it first with dry_run and queue nothing."
          >
            <RequestFlow />
            <Panel>
              <SectionHeading
                kicker="Step 3 · Wait, or poll yourself"
                title="Block, or estimate first"
                desc="wait= blocks for a finished result inline (ceiling 300s, never the documented default for anything but a small direct run). dry_run=true estimates without spending any compute."
              />
              <CodeBlock code={lang.polling} label={lang.id} />
            </Panel>
            <div className="grid gap-3 sm:grid-cols-2">
              <StatTile value="~1 min" label="12,000 designs (top-50 genes, pairs) — a typical direct run." />
              <StatTile value="~55 hrs" label="13,000,000 designs (top-200 genes, triples) — needs budget, not wait=." />
            </div>
            <p className="text-xs text-muted-foreground">
              Both figures are ~15 ms/design on one core — a rough estimate, never a guarantee.
              Always confirm with <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[11px]">dry_run=true</code> before
              committing a large sweep to the queue.
            </p>
          </Section>

          <Section
            id="objects"
            kicker="How it works"
            title="Client, Job & Artifact"
            desc="Three objects, every client. A Client holds a key and submits; a Job is one submitted design and everything it produced; an Artifact is one file on it."
          >
            <ObjectMap />
            <ul className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
              <li><span className="font-medium text-foreground">Client</span> — stateless besides the key and base URL. One per script, reused for every call.</li>
              <li><span className="font-medium text-foreground">Job</span> — returned by <code className="font-mono text-xs">design()</code>. Already resolved if the server answered inline.</li>
              <li><span className="font-medium text-foreground">Candidate</span> — one ranked design. <code className="font-mono text-xs">top_n</code> of them per job, best first.</li>
              <li><span className="font-medium text-foreground">Metric</span> — one of the nine scored measurements on a candidate. See Scoring below.</li>
              <li><span className="font-medium text-foreground">Artifact</span> — one output file (FASTA, an SVG structure render, …), fetched fresh on request.</li>
            </ul>
          </Section>

          <Section
            id="scoring"
            kicker="How it works"
            title="Scoring & the 9 metrics"
            desc="Re-weighting the nine metrics is the most scientifically interesting thing this API offers — “rank these by leakage, I don't care about GC.” It's also the fastest way to make a score uninterpretable, so four rules keep it safe."
          >
            <div className="overflow-hidden rounded-xl border border-border">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border bg-surface text-[11px] uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3">Rule</th>
                    <th className="px-4 py-3">Why</th>
                  </tr>
                </thead>
                <tbody>
                  {SCORING_RULES.map((r) => (
                    <tr key={r.rule} className="border-b border-border bg-card last:border-b-0">
                      <td className="w-[38%] px-4 py-3 text-sm font-medium text-foreground">{r.rule}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{r.why}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Panel>
              <div className="mb-4 flex items-baseline justify-between gap-3">
                <div className="text-sm font-medium text-foreground">DEFAULT_V1 weights</div>
                <div className="font-mono text-[11px] text-muted-foreground">weight × direction</div>
              </div>
              <MetricsChart />
            </Panel>

            <div className="overflow-x-auto rounded-xl border border-border">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border bg-surface text-[11px] uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3 font-mono">Metric</th>
                    <th className="px-4 py-3">Direction</th>
                    <th className="px-4 py-3">Weight</th>
                    <th className="px-4 py-3">Valid range</th>
                    <th className="px-4 py-3">Unit</th>
                    <th className="px-4 py-3">Meaning</th>
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map((m) => (
                    <tr key={m.name} className="border-b border-border bg-card last:border-b-0">
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-foreground">{m.name}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">
                        {m.direction === "higher" ? "↑ higher better" : "↓ lower better"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-foreground">{m.weight.toFixed(1)}</td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-muted-foreground">
                        {m.validRange[0]} – {m.validRange[1]}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">{m.unit}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{m.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="rounded-xl border border-border bg-surface p-5 text-sm text-muted-foreground">
              <span className="font-medium text-foreground">Hard filters (always applied, before ranking):</span>{" "}
              <code className="font-mono text-xs">predicted_leakage</code> max 0.85 ·{" "}
              <code className="font-mono text-xs">state_separation</code> min 0.5.{" "}
              <span className="font-medium text-foreground">Tie-breakers, in order:</span>{" "}
              <code className="font-mono text-xs">state_separation</code>, then{" "}
              <code className="font-mono text-xs">predicted_leakage</code>.
            </div>
          </Section>

          <Section
            id="parameters"
            kicker="Reference"
            title="Every request field"
            desc="What POST /api/design accepts — the same body regardless of which client sends it. Nested objects (constraints, scoring, budget, payload) are broken out below so every argument gets its own explanation."
          >
            <Panel>
              <CodeBlock code={lang.full} label={lang.id} title="the full request" />
            </Panel>
            <ParamTable rows={PARAMETERS} />

            <div className="space-y-8 pt-2">
              <div>
                <h4 className="mb-2 font-mono text-sm font-semibold text-foreground">constraints{"{ }"}</h4>
                <p className="mb-3 text-sm text-muted-foreground">Search constraints — domain.Constraints, field for field.</p>
                <ParamTable rows={CONSTRAINTS_FIELDS} dense />
              </div>
              <div>
                <h4 className="mb-2 font-mono text-sm font-semibold text-foreground">scoring{"{ }"}</h4>
                <p className="mb-3 text-sm text-muted-foreground">How candidates are compared for this run — see the Scoring section above.</p>
                <ParamTable rows={SCORING_FIELDS} dense />
              </div>
              <div>
                <h4 className="mb-2 font-mono text-sm font-semibold text-foreground">budget{"{ }"}</h4>
                <p className="mb-3 text-sm text-muted-foreground">A cost ceiling — the search space is unbounded without one.</p>
                <ParamTable rows={BUDGET_FIELDS} dense />
              </div>
              <div>
                <h4 className="mb-2 font-mono text-sm font-semibold text-foreground">payload{"{ }"}</h4>
                <p className="mb-3 text-sm text-muted-foreground">What the circuit expresses.</p>
                <ParamTable rows={PAYLOAD_FIELDS} dense />
              </div>
            </div>
          </Section>

          <Section
            id="query-params"
            kicker="Reference"
            title="Query parameters"
            desc="The two switches that change what POST /api/design does with the same body."
          >
            <div className="overflow-hidden rounded-xl border border-border">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border bg-surface text-[11px] uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3 font-mono">Query parameter</th>
                    <th className="px-4 py-3">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {QUERY_PARAMS.map((q) => (
                    <tr key={q.field} className="border-b border-border bg-card last:border-b-0">
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-foreground">{q.field}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{q.notes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section
            id="errors"
            kicker="Reference"
            title="One shape, every language"
            desc="Every failure — a bad key, a typo, a rate limit, a failed run — comes back as the same envelope, mapped to a typed error in each client."
          >
            <Panel>
              <CodeBlock code={lang.errors} label={lang.id} />
            </Panel>
            <div className="overflow-hidden rounded-xl border border-border">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border bg-surface text-[11px] uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3 font-mono">Status</th>
                    <th className="px-4 py-3 font-mono">Code</th>
                    <th className="px-4 py-3">When</th>
                  </tr>
                </thead>
                <tbody>
                  {ERROR_CODES.map((e) => (
                    <tr key={e.code} className="border-b border-border bg-card last:border-b-0">
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-foreground">{e.status}</td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-foreground">{e.code}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{e.when}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section
            id="functions"
            kicker="Reference"
            title="Functions & methods"
            desc={`Every function the ${lang.label} client exposes, with its arguments — not just what a code sample happens to call.`}
          >
            {active === "curl" ? (
              <Panel>
                <p className="text-sm text-muted-foreground">
                  curl talks directly to the five endpoints — there is no client object to
                  document. See the table in{" "}
                  <a href="#rest-api" className="text-mint hover:underline">Full REST API</a> below.
                </p>
              </Panel>
            ) : (
              <ClientReferenceView language={active} />
            )}
          </Section>

          <Section
            id="rest-api"
            kicker="Reference"
            title="Every client wraps the same five calls"
            desc="The REST API is the product; the packages are thin, idiomatic sugar over these. Anyone needing more of the platform — datasets, annotations, API keys — talks to the full 35-endpoint API directly."
          >
            <div className="overflow-hidden rounded-xl border border-border">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border bg-surface text-[11px] uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3 font-mono">Method</th>
                    <th className="px-4 py-3 font-mono">Path</th>
                    <th className="px-4 py-3">Purpose</th>
                  </tr>
                </thead>
                <tbody>
                  {REST_ENDPOINTS.map((e) => (
                    <tr key={e.path} className="border-b border-border bg-card last:border-b-0">
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-mint">{e.method}</td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-foreground">{e.path}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{e.purpose}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Panel>
              <div className="flex items-start gap-3">
                <Terminal className="mt-0.5 h-5 w-5 shrink-0 text-mint" />
                <p className="text-sm text-muted-foreground">
                  Both are self-describing and always current:{" "}
                  <a href="/api/docs" className="text-mint hover:underline">interactive docs</a> and{" "}
                  <a href="/api/openapi.json" className="text-mint hover:underline">the OpenAPI schema</a> — generate a
                  client in any language the three shipped ones don't cover.
                </p>
              </div>
            </Panel>
          </Section>

          <Section
            id="recipe-deseq2"
            kicker="Recipe · R"
            title="DESeq2 output to plasmid design, in one script"
            desc="The single most persuasive interoperability demo here — no CSV round trip, no manual export."
          >
            <Panel>
              <CodeBlock code={DESEQ2_RECIPE} label="r" />
            </Panel>
          </Section>

          <Section
            id="recipe-sweep"
            kicker="Recipe · Python"
            title="Cost a whole sweep before running any of it"
            desc="A dry_run client makes every design() call an estimate — sweep every organism or constraint set you're considering, then submit only the one you want."
          >
            <Panel>
              <CodeBlock code={SWEEP_RECIPE} label="python" />
            </Panel>
          </Section>

          <Section
            id="recipe-scoring"
            kicker="Recipe · Python"
            title="Re-weight the scoring, don't rebuild it"
            desc="weight: 0.0 is how you say “ignore this metric” — the raw value stays measured and visible, it just stops moving the rank."
          >
            <Panel>
              <CodeBlock code={SCORING_RECIPE} label="python" />
            </Panel>
          </Section>

          <Section
            id="notebook"
            kicker="Recipe · Jupyter"
            title="A ready-to-run notebook"
            desc="Authenticate, submit, cost a sweep, plot the results, download an artifact — the whole quickstart as cells you can run and edit."
          >
            <Panel className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="text-sm font-medium text-foreground">cernal-quickstart.ipynb</div>
                <p className="mt-1 max-w-lg text-sm text-muted-foreground">
                  8 cells: authenticate, a one-call design, a constrained + custom-scored run, a
                  dry_run sweep, a matplotlib chart of the top candidates, and an artifact download.
                </p>
              </div>
              <a
                href={NOTEBOOK_URL}
                download
                className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-gradient-mint px-4 py-2.5 text-sm font-medium text-mint-foreground shadow-mint hover:opacity-90"
              >
                <Download className="h-4 w-4" /> Download notebook
              </a>
            </Panel>

            <div className="overflow-hidden rounded-xl border border-border bg-card">
              <div className="border-b border-border bg-surface px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                Preview
              </div>
              <div className="space-y-0 divide-y divide-border">
                <div className="grid grid-cols-[auto_1fr] gap-4 px-4 py-4">
                  <span className="pt-0.5 font-mono text-[11px] text-muted-foreground">¶</span>
                  <p className="text-sm text-muted-foreground">
                    <span className="font-medium text-foreground">A ranked design, in one call</span> — Job.wait()
                    polls with backoff until the run finishes. to_dataframe() needs pandas.
                  </p>
                </div>
                <div className="grid grid-cols-[auto_1fr] gap-4 px-4 py-4">
                  <span className="pt-0.5 font-mono text-[11px] text-mint">In [2]:</span>
                  <CodeBlock
                    code={`job = c.design(trigger_sequence="AUGGCUAAGCUUAACGGAUCC", organism="ecoli")
df = job.wait().to_dataframe()
df.head()`}
                    label="python"
                  />
                </div>
              </div>
            </div>
          </Section>
        </div>
      </div>
    </>
  );
}
