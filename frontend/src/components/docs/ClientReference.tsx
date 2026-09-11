/**
 * Every function/method each client exposes, with its arguments — the piece a code
 * sample alone can't give a first-timer: what else does this object do, and what
 * does each argument actually mean. Mirrors clients/{python,r,matlab}/ verbatim.
 */

interface FnParam {
  name: string;
  type: string;
  default?: string;
  desc: string;
}

interface FnDoc {
  signature: string;
  returns?: string;
  desc: string;
  params?: FnParam[];
}

interface ObjectDoc {
  object: string;
  note?: string;
  fns: FnDoc[];
}

const PYTHON: ObjectDoc[] = [
  {
    object: "Client",
    note: "Holds a key and a base URL. Nothing else here is stateful.",
    fns: [
      {
        signature: "Client(api_key=None, *, base_url, dry_run=False, timeout=30.0, session=None)",
        desc: "Construct a client.",
        params: [
          { name: "api_key", type: "str | None", default: "None", desc: "An X-API-Key secret (cern_live_...). Falls back to the CERNAL_API_KEY environment variable." },
          { name: "base_url", type: "str", default: "required", desc: "The deployment to talk to." },
          { name: "dry_run", type: "bool", default: "False", desc: "When true, every design() call estimates instead of submitting, unless overridden per call." },
          { name: "timeout", type: "float", default: "30.0", desc: "Seconds per HTTP request — not the run itself; see Job.wait()." },
        ],
      },
      {
        signature: "Client.design(*, wait=None, dry_run=None, **fields) -> Job",
        returns: "Job",
        desc: "Submit a design request. Every keyword is a request field (trigger_sequence, organism, constraints, scoring, budget, top_n, seed, …) passed straight through as the JSON body — see \"Every request field\" below for the full list.",
        params: [
          { name: "wait", type: "float | None", default: "None", desc: "Block server-side for a finished result (ceiling 300s)." },
          { name: "dry_run", type: "bool | None", default: "None", desc: "Estimate without submitting for this call only." },
        ],
      },
      { signature: "Client.status(job_id) -> dict", returns: "dict", desc: "GET /api/design/{id} — status, without waiting." },
      { signature: "Client.results(job_id, **query) -> dict", returns: "dict", desc: "Ranked candidates for an already-finished job." },
      { signature: "Client.artifact(artifact_id) -> bytes", returns: "bytes", desc: "Raw bytes of one artifact. Job.artifact(kind).save(path) is usually what you want instead." },
      { signature: "Client.capabilities() -> dict", returns: "dict", desc: "GET /api/version — gate families, scoring metrics and their units. Needs no key." },
    ],
  },
  {
    object: "Job",
    note: "A submitted design, returned by Client.design(). Already resolved if the server answered inline.",
    fns: [
      {
        signature: "Job.wait(*, timeout=300.0, poll=2.0, max_poll=15.0) -> Job",
        returns: "Job",
        desc: "Poll with backoff until the run reaches a terminal state. Raises RunFailed for FAILED/CANCELLED, TimeoutError if timeout elapses first — call wait() again to keep polling; it will not resubmit.",
        params: [
          { name: "timeout", type: "float", default: "300.0", desc: "Overall seconds to wait before raising TimeoutError." },
          { name: "poll", type: "float", default: "2.0", desc: "Initial delay between polls, in seconds." },
          { name: "max_poll", type: "float", default: "15.0", desc: "Ceiling the backoff grows to." },
        ],
      },
      { signature: "Job.status", returns: "str | None", desc: "Property. The job's current status string." },
      { signature: "Job.candidates() -> list[dict]", returns: "list[dict]", desc: "Every returned candidate, ranked." },
      { signature: "Job.best() -> dict | None", returns: "dict | None", desc: "The highest-ranked candidate, or None if every candidate was rejected." },
      { signature: "Job.to_dicts() -> list[dict]", returns: "list[dict]", desc: "Alias of candidates() — always available, no dependency." },
      { signature: "Job.to_dataframe()", returns: "pandas.DataFrame", desc: "Needs pandas: pip install cernal[pandas]. Raises a helpful ImportError otherwise." },
      {
        signature: "Job.artifact(kind) -> Artifact",
        returns: "Artifact",
        desc: "The first artifact of kind (e.g. \"fasta\", \"structure_svg\") on this run, fetched fresh.",
        params: [{ name: "kind", type: "str", desc: "An artifact kind, e.g. \"fasta\" or \"structure_svg\"." }],
      },
      { signature: "Artifact.save(path) -> None", desc: "Downloads and writes the artifact to path." },
    ],
  },
];

const R: ObjectDoc[] = [
  {
    object: "Client & submission",
    fns: [
      {
        signature: "cernal_client(api_key = Sys.getenv(\"CERNAL_API_KEY\"), base_url, timeout = 30)",
        returns: "cernal_client",
        desc: "Construct a client. Holds a key and a base URL.",
        params: [
          { name: "api_key", type: "character", default: "env var", desc: "An X-API-Key secret. Defaults to CERNAL_API_KEY." },
          { name: "base_url", type: "character", default: "required", desc: "The deployment to talk to." },
          { name: "timeout", type: "numeric", default: "30", desc: "Seconds per HTTP request." },
        ],
      },
      {
        signature: "cernal_design(client, ..., wait = NULL, dry_run = FALSE)",
        returns: "cernal_job",
        desc: "Submit a design request. Every named argument in ... is a request field, e.g. trigger_sequence = \"...\", constraints = list(max_triggers = 2L).",
        params: [
          { name: "wait", type: "numeric", default: "NULL", desc: "Seconds to block server-side for a finished result (ceiling 300)." },
          { name: "dry_run", type: "logical", default: "FALSE", desc: "Estimate without submitting." },
        ],
      },
      {
        signature: "cernal_wait(job, timeout = 300, poll = 2, max_poll = 15)",
        returns: "cernal_job",
        desc: "Poll with backoff (2s → max_poll, up to timeout) until the run is terminal.",
      },
      { signature: "cernal_status(client, job_id)", returns: "list", desc: "The status of a job, without waiting." },
      { signature: "cernal_capabilities(client)", returns: "list", desc: "Gate families, scoring metrics and their units. No key needed." },
    ],
  },
  {
    object: "Results",
    fns: [
      { signature: "cernal_results(job)", returns: "tibble", desc: "One row per candidate, metrics decomposed into columns — drops straight into dplyr and ggplot2." },
      { signature: "cernal_best(job)", returns: "tibble | NULL", desc: "The highest-ranked candidate as a one-row tibble." },
      {
        signature: "cernal_artifact(job, kind, path)",
        desc: "Downloads the first artifact of kind and writes it to path.",
        params: [
          { name: "kind", type: "character", desc: "e.g. \"fasta\", \"structure_svg\"." },
          { name: "path", type: "character", desc: "Where to save it." },
        ],
      },
    ],
  },
];

const MATLAB: ObjectDoc[] = [
  {
    object: "cernal.Client",
    fns: [
      {
        signature: "cernal.Client(apiKey, 'BaseURL', url, 'Timeout', 30)",
        desc: "Construct a client. Name-value pairs, MATLAB-style.",
        params: [
          { name: "apiKey", type: "char", default: "getenv('CERNAL_API_KEY')", desc: "An X-API-Key secret." },
          { name: "'BaseURL'", type: "char", default: "required", desc: "The deployment to talk to." },
          { name: "'Timeout'", type: "double", default: "30", desc: "Seconds per HTTP request." },
        ],
      },
      {
        signature: "Client.design(...) -> Job",
        returns: "cernal.Job",
        desc: "Submit a design request. Name-value pairs matching request field names exactly (snake_case, not PascalCase) — 'trigger_sequence', 'constraints' (a struct), etc. 'wait' and 'dry_run' are reserved and not sent as body fields.",
      },
      { signature: "Client.status(jobId) -> struct", returns: "struct", desc: "The status of a job, without waiting." },
      { signature: "Client.results(jobId, ...) -> struct", returns: "struct", desc: "Ranked candidates, raw — Job.results() wraps this into a table." },
      { signature: "Client.capabilities() -> struct", returns: "struct", desc: "Gate families, scoring metrics and their units. No key needed." },
      {
        signature: "Client.downloadArtifact(artifactId, path)",
        desc: "Save one artifact to path.",
        params: [
          { name: "artifactId", type: "char", desc: "An artifact id." },
          { name: "path", type: "char", desc: "Where to save it." },
        ],
      },
    ],
  },
  {
    object: "cernal.Job",
    note: "Returned by Client.design(). Already resolved if the server answered inline.",
    fns: [
      {
        signature: "Job.wait('Timeout', 300, 'Poll', 2, 'MaxPoll', 15) -> Job",
        returns: "cernal.Job",
        desc: "Poll with backoff until the run reaches a terminal state.",
      },
      { signature: "Job.currentStatus() -> string", returns: "string", desc: "The job's current status." },
      { signature: "Job.results() -> table", returns: "table", desc: "Ranked candidates as a MATLAB table — writetable, sortrows, groupsummary all work immediately." },
      { signature: "Job.best() -> table", returns: "table", desc: "The highest-ranked candidate, as a one-row table." },
      {
        signature: "Job.artifact(kind, path)",
        desc: "Save the first artifact of kind to path.",
        params: [
          { name: "kind", type: "char", desc: "e.g. 'fasta', 'structure_svg'." },
          { name: "path", type: "char", desc: "Where to save it." },
        ],
      },
    ],
  },
];

export const CLIENT_REFERENCE: Record<string, ObjectDoc[]> = { python: PYTHON, r: R, matlab: MATLAB };

function FnCard({ fn }: { fn: FnDoc }) {
  return (
    <div className="border-t border-border py-4 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <code className="font-mono text-[13px] font-medium text-foreground">{fn.signature}</code>
        {fn.returns && (
          <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            → {fn.returns}
          </span>
        )}
      </div>
      <p className="mt-1.5 text-sm text-muted-foreground">{fn.desc}</p>
      {fn.params && fn.params.length > 0 && (
        <div className="mt-3 overflow-hidden rounded-lg border border-border">
          <table className="w-full text-left text-xs">
            <tbody>
              {fn.params.map((p) => (
                <tr key={p.name} className="border-b border-border last:border-b-0 even:bg-surface">
                  <td className="whitespace-nowrap px-3 py-1.5 align-top font-mono text-foreground">
                    {p.name}
                  </td>
                  <td className="whitespace-nowrap px-3 py-1.5 align-top font-mono text-muted-foreground">
                    {p.type}
                  </td>
                  <td className="whitespace-nowrap px-3 py-1.5 align-top font-mono text-muted-foreground">
                    {p.default ?? "—"}
                  </td>
                  <td className="px-3 py-1.5 align-top text-muted-foreground">{p.desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function ClientReferenceView({ language }: { language: string }) {
  const groups = CLIENT_REFERENCE[language];
  if (!groups) return null;

  return (
    <div className="space-y-8">
      {groups.map((group) => (
        <div key={group.object}>
          <h3 className="font-mono text-sm font-semibold text-foreground">{group.object}</h3>
          {group.note && <p className="mt-1 text-sm text-muted-foreground">{group.note}</p>}
          <div className="mt-3 rounded-xl border border-border bg-card px-5">
            {group.fns.map((fn) => (
              <FnCard key={fn.signature} fn={fn} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
