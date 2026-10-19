/**
 * Layout primitives shared by every screen, lifted from the Lovable design.
 */

import { CheckCircle2, ChevronRight } from "lucide-react";

/**
 * The wizard's five steps.
 *
 * The design labelled three (Inputs / Payload / Fulfillment) while writing four Step
 * components. Fulfillment is not a wizard step here — it is a run's result page, with
 * its own URL — so "Compile" takes its place on the rail. "Vector" (docs/plasmids.md
 * Q13) was added after: which plasmid backbone the circuit gets assembled onto.
 */
export const steps = [
  { n: 1, label: "Inputs", sub: "Transcriptomic data" },
  { n: 2, label: "Logic", sub: "Switch mechanism" },
  { n: 3, label: "Payload", sub: "Genetic output" },
  { n: 4, label: "Vector", sub: "Plasmid backbone" },
  { n: 5, label: "Compile", sub: "Submit & optimize" },
] as const;

export function StepRail({ active }: { active: number }) {
  return (
    <ol className="flex items-center gap-2">
      {steps.map((s, i) => {
        const isActive = active === s.n;
        const isDone = active > s.n;
        return (
          <li key={s.n} className="flex items-center gap-2">
            <div
              className={`flex items-center gap-3 rounded-lg border px-3 py-2 transition ${
                isActive
                  ? "border-primary/30 bg-primary/5"
                  : isDone
                  ? "border-mint/40 bg-mint/5"
                  : "border-border bg-surface"
              }`}
            >
              <div
                className={`grid h-7 w-7 place-items-center rounded-md font-mono text-xs font-semibold ${
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : isDone
                    ? "bg-mint text-mint-foreground"
                    : "bg-secondary text-muted-foreground"
                }`}
              >
                {isDone ? <CheckCircle2 className="h-4 w-4" /> : s.n.toString().padStart(2, "0")}
              </div>
              <div className="hidden sm:block">
                <div className="text-sm font-medium text-foreground">{s.label}</div>
                <div className="text-[11px] text-muted-foreground">{s.sub}</div>
              </div>
            </div>
            {i < steps.length - 1 && <ChevronRight className="h-4 w-4 text-muted-foreground/40" />}
          </li>
        );
      })}
    </ol>
  );
}

export function SectionHeading({ kicker, title, desc }: { kicker: string; title: string; desc: string }) {
  return (
    <div className="mb-6 flex items-end justify-between gap-6">
      <div>
        <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-mint">{kicker}</div>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-foreground">{title}</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{desc}</p>
      </div>
    </div>
  );
}

export function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-border bg-card p-8 shadow-clinical ${className}`}>
      {children}
    </section>
  );
}

/* ---------- Step 1 ---------- */

