/**
 * Two relationship diagrams, built from flex boxes + connectors rather than SVG —
 * the same idiom Primitives.tsx's StepRail already uses, so it survives line-wrap at
 * phone width without hand-maintained coordinates.
 */

import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  Database,
  FileDown,
  FlaskConical,
  Gauge,
  ListChecks,
  Rows3,
  Send,
} from "lucide-react";
import type { ReactNode } from "react";

function Node({
  icon,
  label,
  sub,
  tone = "default",
}: {
  icon: ReactNode;
  label: string;
  sub: string;
  tone?: "default" | "mint" | "dashed";
}) {
  return (
    <div
      className={`flex min-w-[168px] items-center gap-3 rounded-lg border px-3 py-2.5 ${
        tone === "mint"
          ? "border-mint/40 bg-mint/5"
          : tone === "dashed"
          ? "border-dashed border-border bg-surface"
          : "border-border bg-card"
      }`}
    >
      <div
        className={`grid h-8 w-8 shrink-0 place-items-center rounded-md ${
          tone === "mint" ? "bg-mint text-mint-foreground" : "bg-secondary text-muted-foreground"
        }`}
      >
        {icon}
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-foreground">{label}</div>
        <div className="truncate font-mono text-[10.5px] text-muted-foreground">{sub}</div>
      </div>
    </div>
  );
}

function Connector({ label }: { label?: string }) {
  return (
    <div className="flex shrink-0 flex-col items-center justify-center px-1 text-muted-foreground/50">
      <ArrowRight className="h-4 w-4" />
      {label && (
        <span className="mt-0.5 whitespace-nowrap font-mono text-[9.5px] text-muted-foreground/70">
          {label}
        </span>
      )}
    </div>
  );
}

/** The request lifecycle: submit → queue → (poll or wait) → results, with the dry_run branch. */
export function RequestFlow() {
  return (
    <div className="space-y-5 overflow-x-auto rounded-xl border border-border bg-surface p-5">
      <div className="flex min-w-max items-center">
        <Node icon={<Send className="h-4 w-4" />} label="Client.design(…)" sub="one call" />
        <Connector label="POST" />
        <Node icon={<Database className="h-4 w-4" />} label="/api/design" sub="202 · QUEUED" />
        <Connector />
        <Node
          icon={<Clock3 className="h-4 w-4" />}
          label="poll, or wait="
          sub="GET /api/design/{id}"
        />
        <Connector />
        <Node
          icon={<CheckCircle2 className="h-4 w-4" />}
          label="COMPLETED"
          sub="/results"
          tone="mint"
        />
        <Connector />
        <Node icon={<Rows3 className="h-4 w-4" />} label="job.candidates()" sub="ranked, best first" />
      </div>

      <div className="flex min-w-max items-center pl-[188px]">
        <div className="mr-1 font-mono text-[10px] text-muted-foreground/60">?dry_run=true</div>
        <Connector />
        <Node
          icon={<Gauge className="h-4 w-4" />}
          label="estimate only"
          sub="200 · nothing queued"
          tone="dashed"
        />
      </div>
    </div>
  );
}

/** What each object owns, and how many of the next thing it holds — Client 1 → Job N → Candidate top_n → Metric ×9. */
export function ObjectMap() {
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-surface p-5">
      <div className="min-w-max space-y-1">
        <Node icon={<FlaskConical className="h-4 w-4" />} label="Client" sub="holds a key + base_url" />

        <div className="ml-4 border-l border-dashed border-border pl-5">
          <div className="py-1.5 font-mono text-[10.5px] text-muted-foreground">.design() → 1 Job</div>
          <Node icon={<Send className="h-4 w-4" />} label="Job" sub="job_id, status, estimate" />

          <div className="ml-4 mt-1.5 space-y-1.5 border-l border-dashed border-border pl-5">
            <div>
              <div className="py-1 font-mono text-[10.5px] text-muted-foreground">
                .candidates() → top_n Candidates, ranked
              </div>
              <Node icon={<ListChecks className="h-4 w-4" />} label="Candidate" sub="rank, overall_score, output" />
              <div className="ml-4 mt-1.5 border-l border-dashed border-border pl-5">
                <div className="py-1 font-mono text-[10.5px] text-muted-foreground">
                  .metrics → 9 Metrics (§ scoring)
                </div>
                <Node icon={<Gauge className="h-4 w-4" />} label="Metric" sub="raw_value, weight, direction" />
              </div>
            </div>

            <div>
              <div className="py-1 font-mono text-[10.5px] text-muted-foreground">
                .artifact(kind) → 1 Artifact
              </div>
              <Node icon={<FileDown className="h-4 w-4" />} label="Artifact" sub=".save(path) writes it to disk" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
