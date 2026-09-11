import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { BookMarked, KeyRound, Terminal } from "lucide-react";

import { AppShell, PageHeader } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Panel, SectionHeading } from "@/components/layout/Primitives";
import { CodeBlock } from "@/components/docs/CodeBlock";

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

# cost a whole sweep before running any of it
cheap = Client(api_key=os.environ["CERNAL_API_KEY"], base_url="https://your-cernal-host",
               dry_run=True)
for organism in ("ecoli", "yeast"):
    print(cheap.design(trigger_sequence=seq, organism=organism).estimate)`,
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

# DESeq2 output to plasmid design in one script
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

const PARAMETERS: Array<{ field: string; type: string; default: string; notes: string }> = [
  { field: "trigger_sequence", type: "string", default: '""', notes: "Direct mode: the mRNA, pasted. Exactly one of these three input fields." },
  { field: "dataset_id", type: "uuid", default: "null", notes: "DE mode: an existing, VALID dataset in this project." },
  { field: "dge_csv", type: "string", default: '""', notes: "DE mode: an inline differential-expression table — creates a dataset." },
  { field: "project", type: "string", default: '""', notes: "Name or UUID. Created automatically if omitted." },
  { field: "organism", type: "string", default: '""', notes: "Only used when a new project is created." },
  { field: "gate_families", type: "string[] | null", default: "null (all available)", notes: "Which switch chemistries may be used." },
  { field: "exclude_gate_families", type: "string[]", default: "[]", notes: "Alternative phrasing: allow every available family except these." },
  { field: "constraints", type: "object", default: "{}", notes: "max_triggers, min_separation, max_p_adj, trigger_lengths, max_switch_length, forbidden_motifs, standard." },
  { field: "scoring", type: "object", default: "{}", notes: "weights, hard_filters, tie_breakers — re-weight the nine metrics, per run." },
  { field: "budget", type: "object", default: "{}", notes: "max_designs, max_runtime_seconds, on_exceed." },
  { field: "payload", type: "object", default: "{}", notes: "outputs, custom_sequence — what the circuit expresses." },
  { field: "top_n", type: "integer", default: "25", notes: "How many ranked candidates the results endpoint returns." },
  { field: "include_rejected", type: "boolean", default: "false", notes: "Include candidates a hard filter disqualified, with their reason." },
  { field: "include_metrics", type: "boolean", default: "true", notes: "Embed the full metric decomposition per candidate." },
  { field: "include_artifacts", type: "string[]", default: "[]", notes: 'Artifact kinds to embed, e.g. ["fasta", "structure_svg"].' },
  { field: "seed", type: "integer | null", default: "null", notes: "Reproducibility — same seed and inputs, same candidates." },
  { field: "idempotency_key", type: "string | null", default: "null", notes: "Resubmitting with the same key returns the existing run." },
  { field: "strict", type: "boolean", default: "true", notes: "An unknown key in constraints/scoring/budget/payload is a 422 with did_you_mean." },
  { field: "notes", type: "string", default: '""', notes: "Free text, echoed back — not read by the engine." },
];

const QUERY_PARAMS = [
  { field: "?wait=<seconds>", notes: "Block server-side for a finished result (ceiling 300s). Falls back to 202 on timeout." },
  { field: "?dry_run=true", notes: "Estimate designs and runtime without submitting — makes no database writes at all." },
];

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

      <div className="mb-8 flex items-center gap-1 rounded-xl border border-border bg-surface p-1">
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

      <div className="space-y-6">
        {lang.install && (
          <Panel>
            <SectionHeading
              kicker="1 · Install"
              title="Get the client"
              desc="A thin wrapper over five HTTP calls — not a generated mirror of the whole API."
            />
            <CodeBlock code={lang.install} label="shell" />
          </Panel>
        )}

        <Panel>
          <SectionHeading
            kicker={lang.install ? "2 · Authenticate" : "1 · Authenticate"}
            title="Hold a key"
            desc="Mint one from the API Keys page — it authenticates every call below, in place of a login."
          />
          <CodeBlock code={lang.authenticate} label={lang.id} />
        </Panel>

        <Panel>
          <SectionHeading
            kicker={lang.install ? "3 · Submit" : "2 · Submit"}
            title="A ranked design, in one call"
            desc="A trigger sequence goes in; ranked candidates, best first, come out."
          />
          <CodeBlock code={lang.quick} label={lang.id} />
        </Panel>

        <Panel>
          <SectionHeading
            kicker="Every field"
            title="The full request"
            desc="Constrained search, custom scoring, and a cost ceiling — every field maps to a row in the reference table below."
          />
          <CodeBlock code={lang.full} label={lang.id} />
        </Panel>

        <Panel>
          <SectionHeading
            kicker="Waiting & estimating"
            title="Block, or cost it first"
            desc="wait= blocks for a finished result inline; dry_run estimates without spending any compute."
          />
          <CodeBlock code={lang.polling} label={lang.id} />
        </Panel>

        <Panel>
          <SectionHeading
            kicker="Errors"
            title="One shape, every language"
            desc="Every failure — a bad key, a typo, a rate limit, a failed run — comes back as the same envelope, mapped to a typed error in each client."
          />
          <CodeBlock code={lang.errors} label={lang.id} />
        </Panel>
      </div>

      <div className="mt-12">
        <SectionHeading
          kicker="Reference"
          title="Every request field"
          desc="What POST /api/design accepts — the same body regardless of which client sends it."
        />
        <div className="overflow-hidden rounded-xl border border-border">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border bg-surface text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-3 font-mono">Field</th>
                <th className="px-4 py-3 font-mono">Type</th>
                <th className="px-4 py-3 font-mono">Default</th>
                <th className="px-4 py-3">Notes</th>
              </tr>
            </thead>
            <tbody>
              {PARAMETERS.map((p) => (
                <tr key={p.field} className="border-b border-border bg-card last:border-b-0">
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-foreground">
                    {p.field}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-muted-foreground">
                    {p.type}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-muted-foreground">
                    {p.default}
                  </td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">{p.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-4 overflow-hidden rounded-xl border border-border">
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
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-foreground">
                    {q.field}
                  </td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">{q.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Panel className="mt-8">
        <div className="flex items-start gap-3">
          <Terminal className="mt-0.5 h-5 w-5 shrink-0 text-mint" />
          <div>
            <h3 className="text-sm font-semibold text-foreground">
              Every client wraps the same five calls
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              <code className="rounded bg-secondary px-1 py-0.5 font-mono text-xs">
                POST /api/design
              </code>{" "}
              ·{" "}
              <code className="rounded bg-secondary px-1 py-0.5 font-mono text-xs">
                GET /api/design/&#123;id&#125;
              </code>{" "}
              ·{" "}
              <code className="rounded bg-secondary px-1 py-0.5 font-mono text-xs">
                GET /api/design/&#123;id&#125;/results
              </code>{" "}
              ·{" "}
              <code className="rounded bg-secondary px-1 py-0.5 font-mono text-xs">
                GET /api/artifacts/&#123;id&#125;/download
              </code>{" "}
              ·{" "}
              <code className="rounded bg-secondary px-1 py-0.5 font-mono text-xs">
                GET /api/version
              </code>
              . Anyone needing more of the platform — projects, datasets, annotations —
              talks to the full REST API directly:{" "}
              <a href="/api/docs" className="text-mint hover:underline">
                interactive docs
              </a>{" "}
              and{" "}
              <a href="/api/openapi.json" className="text-mint hover:underline">
                the OpenAPI schema
              </a>{" "}
              are both self-describing and always current.
            </p>
          </div>
        </div>
      </Panel>
    </>
  );
}
