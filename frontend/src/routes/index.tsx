import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect, useRef } from "react";
import {
  Activity,
  ChevronRight,
  CircuitBoard,
  Download,
  FileUp,
  FlaskConical,
  Layers,
  LayoutDashboard,
  Library,
  Settings,
  ShoppingCart,
  Sparkles,
  UploadCloud,
  User,
  Dna,
  CheckCircle2,
  ChevronDown,
} from "lucide-react";
import cernalLogo from "@/assets/cernal-logo-animated.svg";

/* ---------- Bacteria (E. coli) icon ---------- */
function BacteriaIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <rect x="4.5" y="8.5" width="15" height="7" rx="3.5" />
      <circle cx="9" cy="12" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="13" cy="11" r="0.7" fill="currentColor" stroke="none" />
      <circle cx="15.5" cy="13" r="0.8" fill="currentColor" stroke="none" />
      <path d="M4.5 12c-1.2-.6-2-1.4-2.5-2.4" />
      <path d="M4.5 12c-1.2.6-2 1.4-2.5 2.4" />
      <path d="M19.5 12c1.2-.6 2-1.4 2.5-2.4" />
      <path d="M19.5 12c1.2.6 2 1.4 2.5 2.4" />
    </svg>
  );
}

/* ---------- Yeast (budding) icon ---------- */
function YeastIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* mother cell */}
      <ellipse cx="10" cy="13" rx="6" ry="6.5" />
      {/* nucleus */}
      <circle cx="9" cy="13" r="1.6" fill="currentColor" stroke="none" opacity="0.55" />
      {/* daughter bud */}
      <circle className="yeast-bud" cx="18" cy="8.5" r="3.2" />
      <circle cx="18" cy="8" r="0.7" fill="currentColor" stroke="none" opacity="0.55" />
    </svg>
  );
}

/* ---------- Human (waving) icon ---------- */
function HumanIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* head */}
      <circle cx="12" cy="5" r="2.6" />
      {/* body */}
      <path d="M12 8v8" />
      {/* legs */}
      <path d="M12 16l-2.5 5" />
      <path d="M12 16l2.5 5" />
      {/* static arm */}
      <path d="M12 10l-4 4" />
      {/* waving arm — rotates from shoulder */}
      <g className="human-wave" style={{ transformOrigin: "12px 10px" }}>
        <path d="M12 10l4-3" />
        <path d="M16 7l0.5 -1.5" />
      </g>
    </svg>
  );
}

function ShieldBacteriaIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* bacteria (behind shield, upper-right) */}
      <g className="shield-bact">
        <circle cx="22" cy="9" r="4.2" fill="currentColor" stroke="none" opacity="0.9" />
        {/* surface pili / spikes */}
        <g stroke="currentColor" strokeWidth="1.4">
          <line x1="22" y1="3.2" x2="22" y2="5" />
          <line x1="27.6" y1="9" x2="25.8" y2="9" />
          <line x1="22" y1="14.8" x2="22" y2="13" />
          <line x1="16.4" y1="9" x2="18.2" y2="9" />
          <line x1="26.2" y1="5" x2="25" y2="6.2" />
          <line x1="26.2" y1="13" x2="25" y2="11.8" />
          <line x1="17.8" y1="5" x2="19" y2="6.2" />
          <line x1="17.8" y1="13" x2="19" y2="11.8" />
        </g>
        {/* inner specks */}
        <circle cx="20.8" cy="8" r="0.7" fill="hsl(var(--card))" stroke="none" />
        <circle cx="23" cy="10" r="0.6" fill="hsl(var(--card))" stroke="none" />
      </g>
      {/* shield (in front) */}
      <path
        d="M14 6 L4 9 V16 C4 21.5 8 25.5 14 28 C20 25.5 24 21.5 24 16 V9 Z"
        fill="hsl(var(--card))"
      />
      <path d="M14 6 L4 9 V16 C4 21.5 8 25.5 14 28 C20 25.5 24 21.5 24 16 V9 Z" />
      {/* center divider */}
      <path d="M14 7.5 V27" strokeWidth="1.4" />
    </svg>
  );
}

function SkullBonesIcon({ className = "" }: { className?: string }) {
  const Bone = () => (
    <g>
      <rect x="4" y="15" width="24" height="2.2" rx="1.1" />
      <circle cx="5" cy="14.2" r="2.2" />
      <circle cx="5" cy="17.8" r="2.2" />
      <circle cx="27" cy="14.2" r="2.2" />
      <circle cx="27" cy="17.8" r="2.2" />
    </g>
  );
  return (
    <svg
      viewBox="0 0 32 32"
      fill="currentColor"
      className={className}
      aria-hidden="true"
    >
      <g className="reaper-body" transform="rotate(30 16 16)">
        <Bone />
      </g>
      <g className="reaper-scythe" transform="rotate(-30 16 16)">
        <Bone />
      </g>
    </svg>
  );
}

function RnaIcon({ className = "" }: { className?: string }) {
  const dots = Array.from({ length: 40 }, (_, i) => {
    const a = (i / 40) * Math.PI * 2;
    return { x: 16 + Math.cos(a) * 14.6, y: 16 + Math.sin(a) * 14.6 };
  });
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* dotted outer ring */}
      <g className="rna-dots" fill="currentColor" stroke="none">
        {dots.map((d, i) => (
          <circle key={i} cx={d.x} cy={d.y} r="0.55" />
        ))}
      </g>
      {/* solid inner ring */}
      <circle cx="16" cy="16" r="12.4" />
      {/* RNA helix: two crossing strands */}
      <g className="rna-helix" strokeWidth="1.4">
        <path d="M9 9 C 21 12, 11 20, 22 23" />
        <path d="M22 9 C 10 12, 21 20, 9 23" />
        {/* rungs */}
        <path d="M11.2 10.8 L 19.6 10.4" strokeWidth="1" />
        <path d="M13.6 13.2 L 18.6 13.2" strokeWidth="1" />
        <path d="M13.6 16 L 18.6 16" strokeWidth="1" />
        <path d="M13.6 18.8 L 18.6 18.8" strokeWidth="1" />
        <path d="M12.4 21.2 L 20.8 21.6" strokeWidth="1" />
      </g>
    </svg>
  );
}










export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "CERNAL — Biological Compiler" },
      { name: "description", content: "Synthetic biology SaaS for compiling, optimizing, and ordering genetic circuits." },
    ],
  }),
  component: Index,
});

const steps = [
  { n: 1, label: "Inputs", sub: "Transcriptomic data" },
  { n: 2, label: "Payload", sub: "Genetic output" },
  { n: 3, label: "Fulfillment", sub: "Compile & order" },
];

function Nav() {
  const items = ["Dashboard", "Quick Guide", "Use Cases", "About Us"];
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1400px] items-center justify-between px-8">
        <div className="flex items-center gap-10">
          <div className="flex items-center gap-2.5">
            <img
              src={cernalLogo}
              alt="CERNAL — Compiler-like Engine for RNA Logic"
              className="h-9 w-auto"
            />
          </div>
          <nav className="hidden items-center gap-1 md:flex">
            {items.map((it, i) => (
              <a
                key={it}
                href="#"
                className={`rounded-md px-3 py-1.5 text-sm transition ${
                  i === 0
                    ? "bg-secondary text-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {it}
              </a>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-xs md:flex">
            <span className="h-1.5 w-1.5 rounded-full bg-mint" />
            <span className="font-mono text-muted-foreground">TAU iGEM Lab</span>
          </div>
          <button className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground">
            <Settings className="h-4 w-4" />
          </button>
          <div className="grid h-9 w-9 place-items-center rounded-full bg-gradient-mint text-mint-foreground">
            <User className="h-4 w-4" />
          </div>
        </div>
      </div>
    </header>
  );
}

function StepRail({ active }: { active: number }) {
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

function SectionHeading({ kicker, title, desc }: { kicker: string; title: string; desc: string }) {
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

function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-border bg-card p-8 shadow-clinical ${className}`}>
      {children}
    </section>
  );
}

function AdvancedOptions({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-6 overflow-hidden rounded-xl border border-border bg-surface-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-3 text-left transition hover:bg-surface"
      >
        <div className="flex items-center gap-2">
          <Settings className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            Advanced Options
          </span>
        </div>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && <div className="border-t border-border p-5">{children}</div>}
    </div>
  );
}

/* ---------- Step 1 ---------- */
function Step1() {
  const [organism, setOrganism] = useState<"pro" | "yeast" | "mam">("pro");
  const [mode, setMode] = useState<"de" | "direct">("de");
  const [triggerSeq, setTriggerSeq] = useState("");
  const organisms = [
    { k: "pro", label: "E. coli", sub: "", Icon: BacteriaIcon, anim: "animate-bacteria" },
    { k: "yeast", label: "Yeast", sub: "", Icon: YeastIcon, anim: "animate-yeast" },
    { k: "mam", label: "Human", sub: "", Icon: HumanIcon, anim: "animate-human" },
  ] as const;
  const sanitizeRna = (v: string) => v.toUpperCase().replace(/[^ACGU]/g, "");
  return (
    <Panel>
      <SectionHeading
        kicker="Step 01 · Inputs"
        title="Define Transcriptomic Inputs"
        desc="Upload your differential expression analysis results, or skip discovery and provide the exact trigger mRNA sequence directly."
      />

      <div className="mb-6">
        <label className="mb-2 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          Organism System
        </label>
        <div className="inline-flex rounded-lg border border-border bg-surface p-1">
          {organisms.map((o) => (
            <button
              key={o.k}
              onClick={() => setOrganism(o.k)}
              className={`group flex items-center gap-2 rounded-md px-5 py-2.5 text-sm transition ${
                organism === o.k
                  ? "bg-card text-foreground shadow-clinical font-medium"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <o.Icon className={`h-4 w-4 ${o.anim}`} />
              <span>{o.label}</span>
              {o.sub && <span className="text-xs text-muted-foreground">/ {o.sub}</span>}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-6">
        <label className="mb-2 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          Input Mode
        </label>
        <div className="inline-flex rounded-lg border border-border bg-surface p-1">
          <button
            onClick={() => setMode("de")}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm transition ${
              mode === "de"
                ? "bg-card text-foreground shadow-clinical font-medium"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Activity className="h-3.5 w-3.5" />
            Differential Expression
          </button>
          <button
            onClick={() => setMode("direct")}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm transition ${
              mode === "direct"
                ? "bg-card text-foreground shadow-clinical font-medium"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Dna className="h-3.5 w-3.5" />
            Direct Trigger mRNA
          </button>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          {mode === "de"
            ? "Upload your differential expression results — CERNAL assumes fold change is calculated as target / control."
            : "Skip discovery — provide the exact mRNA sequence you want to act as the trigger."}
        </p>
      </div>

      {mode === "de" ? (
        <div className="rounded-xl border-2 border-dashed border-border bg-surface p-6 transition hover:border-mint hover:bg-mint/5">
          <div className="flex items-start justify-between">
            <div className="flex items-start gap-4">
              <div className="grid h-12 w-12 place-items-center rounded-lg bg-gradient-mint shadow-mint">
                <UploadCloud className="h-5 w-5 text-mint-foreground" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-foreground">Differential Expression Results</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Upload a single file containing your DE analysis. Must include a <span className="font-mono text-foreground">fold change</span> column (target / control). Optional columns such as <span className="font-mono text-foreground">p-value</span> or <span className="font-mono text-foreground">padj</span> will be used if present.
                </p>
              </div>
            </div>
            <div className="rounded-md bg-card px-2 py-0.5 font-mono text-[10px] tracking-wider text-muted-foreground">
              DE RESULTS
            </div>
          </div>
          <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
            <FileUp className="h-3.5 w-3.5" />
            <span className="font-mono">.csv · .tsv · .xlsx · max 100MB</span>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button className="rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:border-mint">
              Browse files
            </button>
            <span className="text-xs text-muted-foreground">Required column: fold change · Assumed direction: target / control</span>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border-2 border-dashed border-border bg-surface p-6 transition hover:border-mint hover:bg-mint/5">
          <div className="flex items-start justify-between">
            <div className="flex items-start gap-4">
              <div className="grid h-12 w-12 place-items-center rounded-lg bg-gradient-mint shadow-mint">
                <Dna className="h-5 w-5 text-mint-foreground" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-foreground">Trigger mRNA Sequence</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Paste the mRNA transcript that should activate the riboswitch. CERNAL will design the toehold against it directly.
                </p>
              </div>
            </div>
            <div className="rounded-md bg-card px-2 py-0.5 font-mono text-[10px] tracking-wider text-muted-foreground">
              TRIGGER
            </div>
          </div>
          <textarea
            value={triggerSeq}
            onChange={(e) => setTriggerSeq(sanitizeRna(e.target.value))}
            placeholder="AUGGCUAGCAAGGGCGAGGAGCUGUUC..."
            rows={5}
            className="mt-4 w-full rounded-md border border-border bg-card p-3 font-mono text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-mint focus:outline-none"
          />
          <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
            <span className="font-mono">A · C · G · U only · min 30 nt recommended</span>
            <span className="font-mono">{triggerSeq.length} nt</span>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button className="rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:border-mint">
              <FileUp className="mr-1.5 inline h-3.5 w-3.5" />
              Upload .fasta
            </button>
            <span className="text-xs text-muted-foreground">or paste sequence above</span>
          </div>
        </div>
      )}
    </Panel>
  );
}

/* ---------- Step 2 ---------- */
function Step2() {
  const [engine, setEngine] = useState("toehold");
  return (
    <Panel>
      <SectionHeading
        kicker="Step 02 · Logic"
        title="Intracellular Logic Gate Assembly"
        desc="Configure the Boolean expression that gates payload expression. CERNAL compiles your logic into a thermodynamically stable switch mechanism."
      />

      <div className="rounded-xl border border-border bg-surface-2 p-5">
        <div className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          Boolean Expression
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 font-mono text-sm">
          <span className="text-muted-foreground">IF</span>
          <Token>Set A Transcripts</Token>
          <span className="rounded-md bg-mint/20 px-2 py-1 text-mint">AND</span>
          <span className="rounded-md bg-primary/10 px-2 py-1 text-primary">NOT</span>
          <Token>Set B Transcripts</Token>
          <button className="ml-auto rounded-md border border-border bg-card px-3 py-1.5 text-xs hover:border-mint">
            + Add clause
          </button>
        </div>
      </div>

      <div className="mt-6">
        <div className="mb-3 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          Core Switch Mechanism
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {[
            { k: "toehold", title: "Toehold Riboswitch", sub: "Translational control · pre-mRNA" },
            { k: "crispr", title: "CRISPR-Cas sgRNA Gate", sub: "Transcriptional control · iSBH" },
            { k: "antisense", title: "Antisense Repression", sub: "Post-transcriptional silencing" },
          ].map((o) => {
            const active = engine === o.k;
            return (
              <button
                key={o.k}
                onClick={() => setEngine(o.k)}
                className={`flex items-start gap-3 rounded-xl border p-4 text-left transition ${
                  active
                    ? "border-mint bg-mint/5 shadow-mint"
                    : "border-border bg-surface hover:border-mint/50"
                }`}
              >
                <div
                  className={`mt-1 grid h-4 w-4 place-items-center rounded-full border-2 ${
                    active ? "border-mint" : "border-muted-foreground/40"
                  }`}
                >
                  {active && <div className="h-1.5 w-1.5 rounded-full bg-mint" />}
                </div>
                <div>
                  <div className="text-sm font-semibold text-foreground">{o.title}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{o.sub}</div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <AdvancedOptions>
        <div className="grid gap-4 md:grid-cols-3">
          <SliderRow label="Off-State Leakage Limit" value={0.08} min={0} max={1} />
          <SliderRow label="Folding Energy (MFE) Min" value={-32} min={-60} max={0} unit=" kcal/mol" />
          <SliderRow label="Off-Target Screening" value={85} min={0} max={100} unit="%" />
        </div>
      </AdvancedOptions>
    </Panel>
  );
}

function Token({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-md border border-border bg-card px-2.5 py-1 text-foreground">
      [ {children} ]
    </span>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  unit = "",
  mono,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  unit?: string;
  mono?: boolean;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className={`text-foreground ${mono ? "font-mono" : "font-mono"}`}>
          {value}
          {unit}
        </span>
      </div>
      <div className="relative h-1.5 w-full rounded-full bg-border">
        <div className="absolute h-1.5 rounded-full bg-gradient-mint" style={{ width: `${pct}%` }} />
        <div
          className="absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full border-2 border-mint bg-card shadow-clinical"
          style={{ left: `calc(${pct}% - 7px)` }}
        />
      </div>
    </div>
  );
}

/* ---------- Step 3 ---------- */
function Step3() {
  const reporters = [
    { k: "gfp", name: "GFP", sub: "Green Fluorescent Protein", color: "oklch(0.82 0.18 145)" },
    { k: "mch", name: "mCherry", sub: "Red Fluorescent Protein", color: "oklch(0.65 0.22 25)" },
    { k: "luc", name: "Luciferase", sub: "Bioluminescent readout", color: "oklch(0.85 0.16 90)" },
  ];
  const markers = [
    { k: "amp", name: "Antibiotic Resistance", sub: "AmpR · KanR positive selection", kind: "Positive" },
    { k: "kill", name: "Apoptosis Inducer", sub: "Programmed cell death kill-switch", kind: "Negative" },
  ];
  const [selected, setSelected] = useState<Set<string>>(new Set(["gfp", "amp"]));
  const [customSeq, setCustomSeq] = useState("");
  const customOn = selected.has("custom");
  const toggle = (k: string) => {
    const n = new Set(selected);
    n.has(k) ? n.delete(k) : n.add(k);
    setSelected(n);
  };
  const sanitize = (v: string) => v.toUpperCase().replace(/[^ACGU]/g, "");


  return (
    <Panel>
      <SectionHeading
        kicker="Step 02 · Payload"
        title="Choose Downstream Output"
        desc="Select the downstream output module — visual reporters for validation, functional selective markers for phenotype gating, or your own desired mRNA sequence"
      />

      <div className="space-y-8">
        <div>
          <div className="mb-3 flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5 text-mint" />
            <div className="font-mono text-[11px] uppercase tracking-wider text-foreground">
              Reporting Genes · Visual Validation
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {reporters.map((r) => {
              const on = selected.has(r.k);
              return (
                <button
                  key={r.k}
                  onClick={() => toggle(r.k)}
                  className={`group relative overflow-hidden rounded-xl border p-5 text-left transition ${
                    on ? "border-mint bg-mint/5" : "border-border bg-surface hover:border-mint/40"
                  }`}
                >
                  <div
                    className="absolute -right-6 -top-6 h-20 w-20 rounded-full opacity-30 blur-xl"
                    style={{ backgroundColor: r.color }}
                  />
                  <div className="relative flex items-start justify-between">
                    <div
                      className="h-10 w-10 rounded-full border-2 border-card shadow-clinical"
                      style={{ backgroundColor: r.color }}
                    />
                    <Check on={on} />
                  </div>
                  <div className="relative mt-4">
                    <div className="font-mono text-sm font-semibold text-foreground">{r.name}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{r.sub}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <div className="mb-3 flex items-center gap-2">
            <FlaskConical className="h-3.5 w-3.5 text-primary" />
            <div className="font-mono text-[11px] uppercase tracking-wider text-foreground">
              Selective Markers · Functional Activation
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {markers.map((m) => {
              const on = selected.has(m.k);
              return (
                <button
                  key={m.k}
                  onClick={() => toggle(m.k)}
                  className={`group flex items-start gap-4 rounded-xl border p-5 text-left transition ${
                    on ? "border-mint bg-mint/5" : "border-border bg-surface hover:border-mint/40"
                  }`}
                >
                  <div className="grid h-10 w-10 place-items-center rounded-lg bg-gradient-deep text-primary-foreground">
                    {m.k === "amp" ? (
                      <ShieldBacteriaIcon className="h-6 w-6 animate-shield" />
                    ) : m.k === "kill" ? (
                      <SkullBonesIcon className="h-6 w-6 animate-skull" />
                    ) : (
                      <Layers className="h-4 w-4" />
                    )}
                  </div>

                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-foreground">{m.name}</span>
                      <span
                        className={`rounded-full px-2 py-0.5 font-mono text-[10px] tracking-wider ${
                          m.kind === "Positive"
                            ? "bg-mint/20 text-mint-foreground"
                            : "bg-destructive/10 text-destructive"
                        }`}
                      >
                        {m.kind.toUpperCase()}
                      </span>
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{m.sub}</div>
                  </div>
                  <Check on={on} />
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <div className="mb-3 flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            <div className="font-mono text-[11px] uppercase tracking-wider text-foreground">
              CUSTOM OUTPUT · USER-DEFINED OUTPUT
            </div>
          </div>
          <div
            className={`rounded-xl border p-5 transition ${
              customOn ? "border-mint bg-mint/5" : "border-border bg-surface hover:border-mint/40"
            }`}
          >
            <button
              type="button"
              onClick={() => toggle("custom")}
              className="flex w-full items-start gap-4 text-left"
            >
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-gradient-deep text-primary-foreground">
                <RnaIcon className="h-6 w-6 animate-rna" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-foreground">
                    Insert Your Own Desired Output mRNA Sequence
                  </span>
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 font-mono text-[10px] tracking-wider text-primary">
                    CUSTOM
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  Paste a custom mRNA coding sequence (A · C · G · U) to drive a bespoke downstream payload.
                </div>
              </div>
              <Check on={customOn} />
            </button>

            {customOn && (
              <div className="mt-4 space-y-2">
                <textarea
                  value={customSeq}
                  onChange={(e) => setCustomSeq(sanitize(e.target.value))}
                  placeholder="AUGGCUAGCAAGGGCGAGGAGCUGUUC..."
                  rows={4}
                  className="w-full resize-y rounded-lg border border-border bg-card px-3 py-2 font-mono text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-mint focus:outline-none"
                />
                <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  <span>Length: {customSeq.length} nt</span>
                  <span>{customSeq.length % 3 === 0 && customSeq.length > 0 ? "In-frame ✓" : "Frame: validate ORF"}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}


function Check({ on }: { on: boolean }) {
  return (
    <div
      className={`grid h-5 w-5 place-items-center rounded-md border-2 transition ${
        on ? "border-mint bg-mint" : "border-border bg-card"
      }`}
    >
      {on && <CheckCircle2 className="h-3 w-3 text-mint-foreground" strokeWidth={3} />}
    </div>
  );
}

function CircuitExplanation() {
  const genes = [
    { name: "Gene A", role: "IL-6", state: "Over-expressed", dir: "up" },
    { name: "Gene B", role: "TNF-α", state: "Over-expressed", dir: "up" },
    { name: "Gene C", role: "HIF-1α", state: "Over-expressed", dir: "up" },
    { name: "Gene D", role: "FOXP3", state: "Under-expressed", dir: "down" },
  ];
  return (
    <section className="mt-8 rounded-2xl border border-border bg-surface-2 p-6">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-mint">
            Circuit Explanation
          </div>
          <h3 className="mt-1 text-lg font-semibold tracking-tight text-foreground">
            How your circuit was wired
          </h3>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Differentially expressed transcripts identified by PyDESeq2 are mapped into a Boolean
            gate that triggers your selected payload.
          </p>
        </div>
        <button className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs font-medium text-foreground transition hover:border-mint">
          <Download className="h-3.5 w-3.5" />
          Extended DGE Analysis
        </button>
      </div>

      <div className="mb-5">
        <div className="mb-2 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          Differentially expressed genes
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {genes.map((g) => (
            <div
              key={g.name}
              className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2.5"
            >
              <div
                className={`grid h-8 w-8 place-items-center rounded-md font-mono text-xs font-semibold ${
                  g.dir === "up"
                    ? "bg-mint/15 text-mint"
                    : "bg-primary/10 text-primary"
                }`}
              >
                {g.dir === "up" ? "▲" : "▼"}
              </div>
              <div className="flex-1">
                <div className="text-sm font-semibold text-foreground">{g.name}</div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  {g.role} · {g.state}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-3 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          Logic Circuit
        </div>
        <div className="flex flex-wrap items-center gap-2 font-mono text-sm">
          <span className="text-muted-foreground">IF</span>
          <Token>Gene A</Token>
          <span className="rounded-md bg-mint/20 px-2 py-1 text-mint">AND</span>
          <span className="text-muted-foreground">(</span>
          <Token>Gene B</Token>
          <span className="rounded-md bg-primary/15 px-2 py-1 text-primary">OR</span>
          <Token>Gene C</Token>
          <span className="text-muted-foreground">)</span>
          <span className="rounded-md bg-primary/10 px-2 py-1 text-primary">AND NOT</span>
          <Token>Gene D</Token>
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
          <span className="rounded-md bg-gradient-mint px-3 py-1 text-mint-foreground">EXPRESS · GFP</span>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          When Gene A is active, and either Gene B or Gene C is active, while Gene D remains
          suppressed, the toehold riboswitch unfolds and translates the GFP payload — producing a
          visible green fluorescence signal only inside cells matching the target transcriptomic
          signature.
        </p>
      </div>
    </section>
  );
}

type CandidateLogic = {
  genes: { n: string; role: string; state: "ON" | "OFF"; dir: "up" | "down" }[];
  midGate: "OR" | "AND";
  outerGate: "AND" | "OR";
  invert: boolean;
  output: string;
  caption: string;
};

type Candidate = {
  n: number;
  name: string;
  score: number;
  bp: number;
  leakage: number;
  dynRange: string;
  mfe: number;
  gc: string;
  offTarget: string;
  successRate: string;
  ringColors: { promoter: string; switch: string; payload: string; marker: string; term: string };
  sequencePreview: string;
  logic: CandidateLogic;
};

const CANDIDATES: Candidate[] = [
  {
    n: 1, name: "pCERNAL_v1", score: 98, bp: 4247, leakage: 0.04, dynRange: "412×", mfe: -38.2,
    gc: "52%", offTarget: "97%", successRate: "94%",
    ringColors: { promoter: "var(--mint)", switch: "var(--deep-blue)", payload: "oklch(0.7 0.18 145)", marker: "oklch(0.6 0.18 280)", term: "oklch(0.78 0.14 90)" },
    sequencePreview: "ATCGGATCCGAATTCGAGCTCGGTACCCGGGGATCCTCTAGAGTCGACCTGCAGGCATGCAAGCTTGGCGTAATCATGGTCATAGCTGTTTCCTG",
    logic: {
      genes: [
        { n: "Gene A", role: "IL-6", state: "ON", dir: "up" },
        { n: "Gene B", role: "TNF-α", state: "ON", dir: "up" },
        { n: "Gene C", role: "HIF-1α", state: "ON", dir: "up" },
        { n: "Gene D", role: "FOXP3", state: "OFF", dir: "down" },
      ],
      midGate: "OR", outerGate: "AND", invert: true,
      output: "GFP",
      caption: "IF A AND (B OR C) AND NOT D → EXPRESS GFP",
    },
  },
  {
    n: 2, name: "pCERNAL_v2", score: 94, bp: 3982, leakage: 0.06, dynRange: "338×", mfe: -35.1,
    gc: "49%", offTarget: "93%", successRate: "89%",
    ringColors: { promoter: "var(--mint)", switch: "oklch(0.65 0.18 250)", payload: "oklch(0.7 0.18 145)", marker: "oklch(0.6 0.18 280)", term: "oklch(0.78 0.14 90)" },
    sequencePreview: "GAATTCATGAAAGCAGCATTGCTGATTCTGGCAGCAGCACTGGGTCTGCTGCGTCGTAGCGCACATGGTAGCAGCCATGAAGAAGAA",
    logic: {
      genes: [
        { n: "Gene A", role: "IL-6", state: "ON", dir: "up" },
        { n: "Gene B", role: "TNF-α", state: "ON", dir: "up" },
        { n: "Gene C", role: "HIF-1α", state: "ON", dir: "up" },
        { n: "Gene D", role: "FOXP3", state: "OFF", dir: "down" },
      ],
      midGate: "AND", outerGate: "AND", invert: true,
      output: "GFP",
      caption: "IF A AND (B AND C) AND NOT D → EXPRESS GFP",
    },
  },
  {
    n: 3, name: "pCERNAL_v3", score: 91, bp: 4512, leakage: 0.09, dynRange: "287×", mfe: -33.4,
    gc: "54%", offTarget: "90%", successRate: "85%",
    ringColors: { promoter: "oklch(0.78 0.14 90)", switch: "var(--deep-blue)", payload: "oklch(0.7 0.18 145)", marker: "oklch(0.6 0.18 280)", term: "var(--mint)" },
    sequencePreview: "TTAACTTTAAGAAGGAGATATACATATGGCAGATCTCAATTGGATATCGGCCGGCCACGCGTCGTAGGAGCGCATAGCGATCGATGCAT",
    logic: {
      genes: [
        { n: "Gene A", role: "IL-6", state: "ON", dir: "up" },
        { n: "Gene B", role: "TNF-α", state: "ON", dir: "up" },
        { n: "Gene C", role: "HIF-1α", state: "ON", dir: "up" },
        { n: "Gene D", role: "FOXP3", state: "OFF", dir: "down" },
      ],
      midGate: "OR", outerGate: "OR", invert: true,
      output: "GFP",
      caption: "IF (A OR (B OR C)) AND NOT D → EXPRESS GFP",
    },
  },
  {
    n: 4, name: "pCERNAL_v4", score: 87, bp: 3754, leakage: 0.12, dynRange: "201×", mfe: -29.8,
    gc: "47%", offTarget: "86%", successRate: "78%",
    ringColors: { promoter: "var(--mint)", switch: "var(--deep-blue)", payload: "oklch(0.7 0.18 145)", marker: "oklch(0.78 0.14 90)", term: "oklch(0.6 0.18 280)" },
    sequencePreview: "ATGAGTAAAGGAGAAGAACTTTTCACTGGAGTTGTCCCAATTCTTGTTGAATTAGATGGTGATGTTAATGGGCACAAATTTTCTGTC",
    logic: {
      genes: [
        { n: "Gene A", role: "IL-6", state: "ON", dir: "up" },
        { n: "Gene B", role: "TNF-α", state: "OFF", dir: "down" },
        { n: "Gene C", role: "HIF-1α", state: "ON", dir: "up" },
        { n: "Gene D", role: "FOXP3", state: "OFF", dir: "down" },
      ],
      midGate: "OR", outerGate: "AND", invert: false,
      output: "GFP",
      caption: "IF A AND (B OR C) → EXPRESS GFP",
    },
  },
];

async function exportCandidatesToExcel() {
  const XLSX = await import("xlsx");
  const rows = CANDIDATES.map((c) => ({
    Rank: `#${c.n}`,
    Name: c.name,
    "Score (%)": c.score,
    "Length (bp)": c.bp,
    Leakage: c.leakage,
    "Dynamic Range": c.dynRange,
    "MFE (kcal/mol)": c.mfe,
    "GC Content": c.gc,
    "Off-Target Specificity": c.offTarget,
    "Success Rate": c.successRate,
    "Logic Expression": c.logic.caption,
    "Sequence (5' → 3')": c.sequencePreview,
  }));
  const ws = XLSX.utils.json_to_sheet(rows);
  ws["!cols"] = [
    { wch: 8 }, { wch: 14 }, { wch: 10 }, { wch: 12 }, { wch: 10 }, { wch: 14 },
    { wch: 14 }, { wch: 12 }, { wch: 22 }, { wch: 14 }, { wch: 42 }, { wch: 90 },
  ];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Plasmid Candidates");
  XLSX.writeFile(wb, "cernal_plasmid_candidates.xlsx");
}

function Step4() {
  const [view, setView] = useState<"plasmid" | "logic">("plasmid");
  const [selectedN, setSelectedN] = useState<number>(1);
  const [expandedN, setExpandedN] = useState<number | null>(1);
  const selected = CANDIDATES.find((c) => c.n === selectedN)!;

  // Gate selection for the simulation under the logic circuit.
  // When the user clicks a gate, we lock to it. Otherwise we auto-cycle.
  const [pickedGate, setPickedGate] = useState<"mid" | "outer" | null>(null);
  const [autoGate, setAutoGate] = useState<"mid" | "outer">("mid");
  useEffect(() => {
    if (view !== "logic" || pickedGate !== null) return;
    const id = setInterval(() => {
      setAutoGate((g) => (g === "mid" ? "outer" : "mid"));
    }, 22000);
    return () => clearInterval(id);
  }, [view, pickedGate]);
  const activeGate: "mid" | "outer" = pickedGate ?? autoGate;

  return (
    <Panel className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 grid-clinical opacity-60" />
      <div className="relative">
        <SectionHeading
          kicker="Step 03 · Fulfillment"
          title="Optimized Plasmid Output"
          desc="CERNAL ranked 247 candidate sequences across structural folding, leakage modeling, and off-target screening. Top candidate below."
        />

        <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
          {/* Plasmid / Logic view */}
          <div className="relative rounded-2xl border border-border bg-gradient-to-br from-surface to-card p-6">
            <div className="absolute right-5 top-5 flex items-center gap-2 rounded-full border border-mint/30 bg-mint/10 px-3 py-1 font-mono text-[10px] tracking-wider text-mint">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-mint" />
              COMPILED
            </div>
            <div className="flex items-center justify-between gap-4">
              <div className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                Candidate #{selected.n} · {selected.name} / {view === "plasmid" ? "Plasmid Map" : "Logic Circuit"}
              </div>
            </div>

            <div className="mt-3 inline-flex rounded-lg border border-border bg-surface p-1">
              {([
                { k: "plasmid", label: "Plasmid Map", icon: Dna },
                { k: "logic", label: "View Logic Circuit", icon: CircuitBoard },
              ] as const).map((t) => {
                const Icon = t.icon;
                const active = view === t.k;
                return (
                  <button
                    key={t.k}
                    onClick={() => setView(t.k)}
                    className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-xs transition ${
                      active
                        ? "bg-card text-foreground shadow-clinical font-medium"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {t.label}
                  </button>
                );
              })}
            </div>

            <div className="mt-4 grid place-items-center">
              {view === "plasmid" ? (
                <PlasmidRing candidate={selected} />
              ) : (
                <div className="w-full space-y-5">
                  <div className="mx-auto w-full max-w-[560px]">
                    <LogicCircuitView
                      logic={selected.logic}
                      activeGate={activeGate}
                      onGateClick={(g) =>
                        setPickedGate((cur) => (cur === g ? null : g))
                      }
                    />
                  </div>
                  <div className="relative">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <span className="h-px w-8 bg-border" />
                        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                          Simulating · {activeGate === "mid" ? "Mid Gate" : "Outer Gate"}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
                        {pickedGate ? (
                          <button
                            onClick={() => setPickedGate(null)}
                            className="rounded border border-border bg-surface px-2 py-0.5 hover:text-foreground"
                          >
                            CLEAR · auto-cycle
                          </button>
                        ) : (
                          <span className="rounded border border-dashed border-border px-2 py-0.5">
                            Click a gate above to focus
                          </span>
                        )}
                      </div>
                    </div>
                    <ToeholdSimulation
                      key={`sim-${selected.n}-${activeGate}`}
                      logic={selected.logic}
                      gate={activeGate}
                    />
                  </div>
                </div>
              )}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-center sm:grid-cols-4">
              {[
                { l: "Leakage", v: selected.leakage.toFixed(2) },
                { l: "Dyn. Range", v: selected.dynRange },
                { l: "MFE", v: selected.mfe.toString() },
                { l: "Length", v: `${selected.bp.toLocaleString()} bp` },
              ].map((s) => (
                <div key={s.l} className="rounded-lg border border-border bg-card px-3 py-2">
                  <div className="font-mono text-base font-semibold text-foreground">{s.v}</div>
                  <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    {s.l}
                  </div>
                </div>
              ))}
            </div>
          </div>


          {/* Candidates list */}
          <div>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                Ranked Candidates
              </div>
              <button
                onClick={exportCandidatesToExcel}
                className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1 text-[11px] font-medium text-foreground transition hover:border-mint"
              >
                <Download className="h-3 w-3" />
                Export .xlsx
              </button>
            </div>
            <div className="space-y-2">
              {CANDIDATES.map((c) => {
                const isSelected = selectedN === c.n;
                const isExpanded = expandedN === c.n;
                return (
                  <div key={c.n}>
                    <button
                      onClick={() => {
                        setSelectedN(c.n);
                        setExpandedN(isExpanded ? null : c.n);
                      }}
                      className={`flex w-full items-center gap-4 rounded-xl border p-4 text-left transition ${
                        isSelected ? "border-mint bg-mint/5 shadow-mint" : "border-border bg-surface hover:border-mint/40"
                      }`}
                    >
                      <div
                        className={`grid h-10 w-10 place-items-center rounded-lg font-mono text-sm font-semibold ${
                          isSelected ? "bg-gradient-mint text-mint-foreground" : "bg-secondary text-muted-foreground"
                        }`}
                      >
                        #{c.n}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-foreground">{c.name}</span>
                          {c.n === 1 && (
                            <span className="rounded-full bg-mint/20 px-2 py-0.5 font-mono text-[10px] tracking-wider text-mint-foreground">
                              TOP
                            </span>
                          )}
                          <span className="font-mono text-[10px] text-muted-foreground">
                            {c.bp.toLocaleString()} bp
                          </span>
                        </div>
                        <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-border">
                          <div
                            className={`h-full ${isSelected ? "bg-gradient-mint" : "bg-muted-foreground/40"}`}
                            style={{ width: `${c.score}%` }}
                          />
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-mono text-lg font-semibold text-foreground">{c.score}%</div>
                        <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                          score
                        </div>
                      </div>
                      <ChevronDown
                        className={`h-4 w-4 text-muted-foreground transition-transform ${isExpanded ? "rotate-180" : ""}`}
                      />
                    </button>
                    {isExpanded && (
                      <div className="mt-1 rounded-xl border border-border bg-surface-2 p-4">
                        <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                          Feature Scores
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-center">
                          {[
                            { l: "Leakage", v: c.leakage.toFixed(2) },
                            { l: "Dyn. Range", v: c.dynRange },
                            { l: "MFE", v: `${c.mfe}` },
                            { l: "GC", v: c.gc },
                            { l: "Off-Target", v: c.offTarget },
                            { l: "Success", v: c.successRate },
                          ].map((s) => (
                            <div key={s.l} className="rounded-md border border-border bg-card px-2 py-1.5">
                              <div className="font-mono text-sm font-semibold text-foreground">{s.v}</div>
                              <div className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
                                {s.l}
                              </div>
                            </div>
                          ))}
                        </div>
                        <div className="mt-3 rounded-md border border-border bg-card p-2">
                          <div className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
                            Sequence preview
                          </div>
                          <div className="mt-1 break-all font-mono text-[10px] leading-relaxed text-foreground/80">
                            {c.sequencePreview.slice(0, 90)}…
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Precision Filters (formerly Advanced Options) */}
            <div className="mt-4">
              <PrecisionFilters />
            </div>

            <div className="mt-5 rounded-xl border border-border bg-surface-2 p-4">
              <div className="mb-2 flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                <Activity className="h-3 w-3" /> Compiler log
              </div>
              <div className="space-y-1 font-mono text-[11px] text-muted-foreground">
                <div><span className="text-mint">✓</span> Negative binomial modeling — 1.2s</div>
                <div><span className="text-mint">✓</span> Structural folding iteration — 8.7s</div>
                <div><span className="text-mint">✓</span> Candidate ranking — 0.4s</div>
              </div>
            </div>
          </div>
        </div>

        {/* CTA Footer */}

        <div className="mt-8 flex flex-col gap-3 border-t border-border pt-6 sm:flex-row">
          <button className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-border bg-card px-6 py-4 text-sm font-medium text-foreground transition hover:border-foreground/30 hover:bg-surface">
            <Download className="h-4 w-4" />
            Export GenBank / FASTA Sequences
          </button>
          <button className="group inline-flex flex-[1.4] items-center justify-center gap-3 rounded-xl bg-gradient-deep px-6 py-4 text-sm font-semibold text-primary-foreground shadow-clinical transition hover:opacity-95">
            <ShoppingCart className="h-4 w-4" />
            Order Plasmid with Our Trusted Partner
            <span className="rounded-full bg-mint px-2.5 py-0.5 font-mono text-[10px] tracking-wider text-mint-foreground">
              SHIPS 7D
            </span>
          </button>
        </div>
      </div>
    </Panel>
  );
}

function PrecisionFilters() {
  const [open, setOpen] = useState(false);
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-3 text-left transition hover:bg-surface"
      >
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-mint" />
          <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            Precision Filters
          </span>
        </div>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="border-t border-border p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <SliderRow label="Off-State Leakage Limit" value={0.08} min={0} max={1} />
            <SliderRow label="Folding Energy (MFE) Min" value={-32} min={-60} max={0} unit=" kcal/mol" />
            <SliderRow label="Off-Target Screening" value={85} min={0} max={100} unit="%" />
            <SliderRow label="Success Rate Threshold" value={90} min={0} max={100} unit="%" />
            <SliderRow label="Basepair Length (max)" value={5000} min={1000} max={10000} unit=" bp" />
            <SliderRow label="GC Content (target)" value={50} min={30} max={70} unit="%" />
          </div>
        </div>
      )}
    </div>
  );
}

function LogicCircuitView({
  logic,
  activeGate,
  onGateClick,
}: {
  logic: CandidateLogic;
  activeGate?: "mid" | "outer";
  onGateClick?: (g: "mid" | "outer") => void;
}) {
  const genes = logic.genes.map((g, i) => ({ ...g, y: 50 + i * 80 }));

  const W = 720;
  const H = 460;
  const geneX = 20;
  const geneW = 150;
  const midGateX = 280;
  const invGateX = 280;
  const outerGateX = 460;
  const gateH = 64;
  const outX = 610;

  const midY = (genes[1].y + genes[2].y) / 2 + 18;
  const invY = genes[3].y + 18;
  const outerY = 200;
  const aLineY = genes[0].y + 18;

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full">
        <defs>
          <linearGradient id="upGrad" x1="0" x2="1">
            <stop offset="0" stopColor="var(--mint)" stopOpacity="0.22" />
            <stop offset="1" stopColor="var(--mint)" stopOpacity="0.08" />
          </linearGradient>
          <linearGradient id="downGrad" x1="0" x2="1">
            <stop offset="0" stopColor="var(--deep-blue)" stopOpacity="0.22" />
            <stop offset="1" stopColor="var(--deep-blue)" stopOpacity="0.08" />
          </linearGradient>
          <linearGradient id="outGrad" x1="0" x2="1">
            <stop offset="0" stopColor="var(--mint)" />
            <stop offset="1" stopColor="oklch(0.75 0.2 145)" />
          </linearGradient>
        </defs>

        {/* Gene boxes */}
        {genes.map((g) => (
          <g key={g.n}>
            <rect
              x={geneX}
              y={g.y}
              width={geneW}
              height={36}
              rx={8}
              fill={g.dir === "up" ? "url(#upGrad)" : "url(#downGrad)"}
              stroke={g.dir === "up" ? "var(--mint)" : "var(--deep-blue)"}
              strokeWidth="1.25"
            />
            <text x={geneX + 12} y={g.y + 23} fontSize="14" fontWeight="700" className="fill-foreground" fontFamily="ui-monospace, monospace">
              {g.n}
            </text>
            <text x={geneX + 78} y={g.y + 23} fontSize="11" className="fill-muted-foreground" fontFamily="ui-monospace, monospace">
              {g.role}
            </text>
            <rect x={geneX + geneW - 36} y={g.y + 8} width={28} height={20} rx={4}
              fill={g.state === "ON" ? "var(--mint)" : "var(--deep-blue)"} fillOpacity="0.18"
              stroke={g.state === "ON" ? "var(--mint)" : "var(--deep-blue)"} strokeWidth="1" />
            <text x={geneX + geneW - 22} y={g.y + 22} textAnchor="middle" fontSize="9" fontWeight="800"
              className={g.state === "ON" ? "fill-mint" : "fill-primary"} fontFamily="ui-monospace, monospace">
              {g.state}
            </text>
          </g>
        ))}

        {/* Wires from genes */}
        <path d={`M ${geneX + geneW} ${aLineY} H ${outerGateX - 30} V ${outerY - 22} H ${outerGateX - 8}`} stroke="var(--muted-foreground)" strokeWidth="1.75" fill="none" opacity="0.85" />
        <path d={`M ${geneX + geneW} ${genes[1].y + 18} H ${midGateX - 8}`} stroke="var(--muted-foreground)" strokeWidth="1.75" fill="none" opacity="0.85" />
        <path d={`M ${geneX + geneW} ${genes[2].y + 18} H ${midGateX - 8}`} stroke="var(--muted-foreground)" strokeWidth="1.75" fill="none" opacity="0.85" />
        <path d={`M ${geneX + geneW} ${genes[3].y + 18} H ${invGateX - 8}`} stroke="var(--muted-foreground)" strokeWidth="1.75" fill="none" opacity="0.85" />

        {/* Mid gate (OR or AND) — between B and C */}
        <g
          onClick={() => onGateClick?.("mid")}
          style={{ cursor: onGateClick ? "pointer" : "default" }}
        >
          {activeGate === "mid" && (
            <rect
              x={midGateX - 10} y={midY - gateH / 2 - 10}
              width={92} height={gateH + 20} rx={10}
              fill="var(--mint)" fillOpacity="0.08"
              stroke="var(--mint)" strokeOpacity="0.6" strokeDasharray="4 3"
            />
          )}
          {logic.midGate === "OR" ? (
            <path
              d={`M ${midGateX} ${midY - gateH / 2}
                  Q ${midGateX + 28} ${midY - gateH / 2 + 8} ${midGateX + 72} ${midY}
                  Q ${midGateX + 28} ${midY + gateH / 2 - 8} ${midGateX} ${midY + gateH / 2}
                  Q ${midGateX + 20} ${midY} ${midGateX} ${midY - gateH / 2} Z`}
              fill="var(--mint)" fillOpacity="0.14" stroke="var(--mint)" strokeWidth="1.75"
            />
          ) : (
            <path
              d={`M ${midGateX} ${midY - gateH / 2}
                  H ${midGateX + 32}
                  A ${gateH / 2} ${gateH / 2} 0 0 1 ${midGateX + 32} ${midY + gateH / 2}
                  H ${midGateX} Z`}
              fill="var(--foreground)" fillOpacity="0.08" stroke="var(--foreground)" strokeWidth="1.75"
            />
          )}
          <text x={midGateX + 18} y={midY + 5} fontSize="14" fontWeight="800"
            className={logic.midGate === "OR" ? "fill-mint" : "fill-foreground"} fontFamily="ui-monospace, monospace">
            {logic.midGate}
          </text>
        </g>

        {/* NOT gate (if invert) */}
        {logic.invert && (
          <g>
            <path
              d={`M ${invGateX} ${invY - gateH / 2} L ${invGateX + 56} ${invY} L ${invGateX} ${invY + gateH / 2} Z`}
              fill="var(--primary)" fillOpacity="0.14" stroke="var(--primary)" strokeWidth="1.75"
            />
            <circle cx={invGateX + 62} cy={invY} r="5" fill="var(--background)" stroke="var(--primary)" strokeWidth="1.75" />
            <text x={invGateX + 10} y={invY + 5} fontSize="13" fontWeight="800" className="fill-primary" fontFamily="ui-monospace, monospace">NOT</text>
          </g>
        )}

        {/* mid out → outer gate */}
        <path d={`M ${midGateX + 72} ${midY} H ${outerGateX - 18} V ${outerY + 22} H ${outerGateX - 8}`}
          stroke="var(--muted-foreground)" strokeWidth="1.75" fill="none" opacity="0.85" />
        {logic.invert && (
          <path d={`M ${invGateX + 67} ${invY} H ${outerGateX - 10} V ${outerY + 44} H ${outerGateX - 8}`}
            stroke="var(--primary)" strokeWidth="1.75" fill="none" opacity="0.85" />
        )}

        {/* Outer gate (AND or OR) */}
        <g
          onClick={() => onGateClick?.("outer")}
          style={{ cursor: onGateClick ? "pointer" : "default" }}
        >
          {activeGate === "outer" && (
            <rect
              x={outerGateX - 10} y={outerY - 70}
              width={112} height={140} rx={10}
              fill="var(--mint)" fillOpacity="0.08"
              stroke="var(--mint)" strokeOpacity="0.6" strokeDasharray="4 3"
            />
          )}
          {logic.outerGate === "AND" ? (
            <path
              d={`M ${outerGateX} ${outerY - 56}
                  H ${outerGateX + 34}
                  A 56 56 0 0 1 ${outerGateX + 34} ${outerY + 56}
                  H ${outerGateX} Z`}
              fill="var(--foreground)" fillOpacity="0.08" stroke="var(--foreground)" strokeWidth="1.75"
            />
          ) : (
            <path
              d={`M ${outerGateX} ${outerY - 56}
                  Q ${outerGateX + 36} ${outerY - 48} ${outerGateX + 90} ${outerY}
                  Q ${outerGateX + 36} ${outerY + 48} ${outerGateX} ${outerY + 56}
                  Q ${outerGateX + 26} ${outerY} ${outerGateX} ${outerY - 56} Z`}
              fill="var(--mint)" fillOpacity="0.14" stroke="var(--mint)" strokeWidth="1.75"
            />
          )}
          <text x={outerGateX + 14} y={outerY + 6} fontSize="16" fontWeight="800"
            className={logic.outerGate === "AND" ? "fill-foreground" : "fill-mint"} fontFamily="ui-monospace, monospace">
            {logic.outerGate}
          </text>
        </g>

        {/* Outer gate → output */}
        <path d={`M ${outerGateX + 90} ${outerY} H ${outX - 6}`}
          stroke="url(#outGrad)" strokeWidth="3" fill="none" />

        {/* Output payload */}
        <g>
          <rect x={outX} y={outerY - 28} width={90} height={56} rx={12}
            fill="url(#outGrad)" stroke="var(--mint)" strokeWidth="1.25" />
          <text x={outX + 45} y={outerY - 4} textAnchor="middle" fontSize="11" fontWeight="800"
            fill="var(--mint-foreground)" fontFamily="ui-monospace, monospace">EXPRESS</text>
          <text x={outX + 45} y={outerY + 18} textAnchor="middle" fontSize="20" fontWeight="900"
            fill="var(--mint-foreground)" fontFamily="ui-monospace, monospace">{logic.output}</text>
        </g>

        {/* Caption */}
        <text x={20} y={H - 16} fontSize="13" fontWeight="600" className="fill-foreground" fontFamily="ui-monospace, monospace">
          {logic.caption}
        </text>
      </svg>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] font-mono text-muted-foreground sm:grid-cols-4">
        <div className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-mint" /> Over-expressed</div>
        <div className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-primary" /> Under-expressed</div>
        <div className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full border border-mint" /> Activating gate</div>
        <div className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full border border-primary" /> Inverting gate</div>
      </div>
    </div>
  );
}


const OUTPUT_COLORS: Record<string, string> = {
  GFP: "oklch(0.72 0.18 145)",
  mCherry: "oklch(0.6 0.22 25)",
  RFP: "oklch(0.6 0.22 25)",
  YFP: "oklch(0.82 0.16 95)",
  BFP: "oklch(0.55 0.18 260)",
};

function RNAKey({
  color,
  name,
  x,
  y,
  opacity,
  clashing,
}: {
  color: string;
  name: string;
  x: number;
  y: number;
  opacity: number;
  clashing: boolean;
}) {
  return (
    <g
      style={{
        transform: `translate(${x}px, ${y}px)`,
        opacity,
        transition: "transform 0.6s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.6s ease",
      }}
    >
      <g className={clashing ? "tha-wiggle" : ""}>
        <g style={{ filter: `drop-shadow(0px 0px 6px ${color}aa)` }}>
          <g transform="translate(-10, -38) scale(0.8)">
            <polygon
              points="-8,0 -4,-8 4,-8 8,0 4,8 -4,8"
              fill={`${color}25`}
              stroke={color}
              strokeWidth="1.5"
            />
            <circle cx="0" cy="0" r="1.5" fill={color} />
            <line x1="8" y1="0" x2="24" y2="0" stroke={color} strokeWidth="2" />
            <line x1="16" y1="0" x2="16" y2="5" stroke={color} strokeWidth="2" />
            <line x1="22" y1="0" x2="22" y2="5" stroke={color} strokeWidth="2" />
          </g>
          <line x1="0" y1="0" x2="100" y2="0" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
          {[15, 32.5, 50, 67.5, 85].map((tx, i) => (
            <g key={i}>
              <line x1={tx} y1="0" x2={tx} y2="10" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
              <circle cx={tx} cy="10" r="1.2" fill={color} opacity="0.9" />
            </g>
          ))}
          <text
            x="50"
            y="-8"
            fill={color}
            fontSize="8"
            fontFamily="ui-monospace, monospace"
            fontWeight="bold"
            letterSpacing="2"
            textAnchor="middle"
          >
            SEQ-MATCH
          </text>
        </g>
        <text
          x="50"
          y="-22"
          className="fill-foreground"
          fontSize="9.5"
          fontFamily="ui-monospace, monospace"
          fontWeight="700"
          textAnchor="middle"
          style={{ letterSpacing: 1.5 }}
        >
          {name.toUpperCase()}
        </text>
      </g>
    </g>
  );
}

function ToeholdSimulation({
  logic,
  gate = "mid",
}: {
  logic: CandidateLogic;
  gate?: "mid" | "outer";
}) {
  const gateType: "AND" | "OR" =
    gate === "mid" ? logic.midGate : logic.outerGate;
  const gateLabel = gate === "mid" ? "MID GATE" : "OUTER GATE";
  const keys =
    gate === "mid"
      ? [
          { name: logic.genes[1].role, color: "var(--mint)" },
          { name: logic.genes[2].role, color: "var(--deep-blue)" },
        ]
      : [
          { name: logic.genes[0].role, color: "var(--mint)" },
          { name: "MID_OUT", color: "var(--deep-blue)" },
        ];
  const output = {
    name: logic.output,
    color: OUTPUT_COLORS[logic.output] ?? "var(--mint)",
  };
  const playbackSpeed = 1.0;

  const [phase, setPhase] = useState(0);
  const [paused, setPaused] = useState(false);
  const phaseRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const andPhases = [
    { id: "LOCKED", duration: 1800, text: "LOCKED · Stem-loop blocks the ribosome binding site." },
    { id: "WRONG_APP", duration: 1300, text: "TEST · Off-target RNA approaches." },
    { id: "WRONG_FAIL", duration: 2200, text: "MISMATCH · Sequence fails to hybridize." },
    { id: "WRONG_REJ", duration: 1300, text: "REJECTED · Off-target dissociates." },
    { id: "A_APP", duration: 1300, text: `AND TEST · ${keys[0].name} approaches toehold.` },
    { id: "A_FAIL", duration: 2200, text: `INSUFFICIENT · ${keys[0].name} alone cannot melt the stem.` },
    { id: "A_REJ", duration: 1300, text: `REJECTED · ${keys[0].name} dissociates.` },
    { id: "B_APP", duration: 1300, text: `AND TEST · ${keys[1].name} approaches toehold.` },
    { id: "B_FAIL", duration: 2200, text: `INSUFFICIENT · ${keys[1].name} alone cannot melt the stem.` },
    { id: "B_REJ", duration: 1300, text: `REJECTED · ${keys[1].name} dissociates.` },
    { id: "BOTH_APP", duration: 1800, text: "COOPERATIVE · Both keys dock simultaneously." },
    { id: "UNLOCK", duration: 2200, text: "UNLOCKED · Dual hybridization melts the stem." },
    { id: "TRANSLATE", duration: 5000, text: `TRANSLATING · Ribosome synthesizes ${output.name}.` },
    { id: "RESET", duration: 1300, text: "Resetting logic gate…" },
  ];
  const orPhases = [
    { id: "LOCKED", duration: 1800, text: "LOCKED · Stem-loop blocks the ribosome binding site." },
    { id: "WRONG_APP", duration: 1300, text: "TEST · Off-target RNA approaches." },
    { id: "WRONG_FAIL", duration: 2200, text: "MISMATCH · Sequence fails to hybridize." },
    { id: "WRONG_REJ", duration: 1300, text: "REJECTED · Off-target dissociates." },
    { id: "A_APP", duration: 1300, text: `OR TEST · ${keys[0].name} approaches toehold.` },
    { id: "A_UNLOCK", duration: 2200, text: `SUCCESS · ${keys[0].name} melts the stem.` },
    { id: "A_TRANS", duration: 5000, text: `TRANSLATING · ${output.name} via ${keys[0].name}.` },
    { id: "A_RESET", duration: 1300, text: "Resetting…" },
    { id: "B_APP", duration: 1300, text: `OR TEST · ${keys[1].name} approaches toehold.` },
    { id: "B_UNLOCK", duration: 2200, text: `SUCCESS · ${keys[1].name} melts the stem.` },
    { id: "B_TRANS", duration: 5000, text: `TRANSLATING · ${output.name} via ${keys[1].name}.` },
    { id: "RESET", duration: 1300, text: "Resetting logic gate…" },
  ];
  const activePhases = gateType === "AND" ? andPhases : orPhases;

  useEffect(() => {
    if (paused) {
      if (timerRef.current) clearTimeout(timerRef.current);
      return;
    }
    const run = () => {
      const d = activePhases[phaseRef.current].duration / playbackSpeed;
      timerRef.current = setTimeout(() => {
        const next = (phaseRef.current + 1) % activePhases.length;
        phaseRef.current = next;
        setPhase(next);
        run();
      }, d);
    };
    run();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused, gateType]);

  const isUnlocked =
    gateType === "AND"
      ? phase === 11 || phase === 12
      : phase === 5 || phase === 6 || phase === 9 || phase === 10;
  const isTranslating = gateType === "AND" ? phase === 12 : phase === 6 || phase === 10;

  const rbsPos = isUnlocked ? { x: 445, y: 300 } : { x: 280, y: 115 };
  const startPos = isUnlocked ? { x: 560, y: 300 } : { x: 310, y: 220 };
  const pathD = isUnlocked
    ? "M 50 300 L 250 300 L 400 300 C 430 300, 460 300, 490 300 L 640 300 L 850 300"
    : "M 50 300 L 250 300 L 250 150 C 250 80, 310 80, 310 150 L 310 300 L 750 300";

  let wrongKey = { x: 100, y: 150, opacity: 0, clashing: false };
  let key1 = { x: 50, y: 150, opacity: 0, clashing: false };
  let key2 = { x: 150, y: 150, opacity: 0, clashing: false };
  if (gateType === "AND") {
    switch (phase) {
      case 1: wrongKey = { x: 100, y: 286, opacity: 1, clashing: false }; break;
      case 2: wrongKey = { x: 100, y: 286, opacity: 1, clashing: true }; break;
      case 3: wrongKey = { x: 100, y: 150, opacity: 0, clashing: false }; break;
      case 4: key1 = { x: 50, y: 286, opacity: 1, clashing: false }; break;
      case 5: key1 = { x: 50, y: 286, opacity: 1, clashing: true }; break;
      case 6: key1 = { x: 50, y: 150, opacity: 0, clashing: false }; break;
      case 7: key2 = { x: 150, y: 286, opacity: 1, clashing: false }; break;
      case 8: key2 = { x: 150, y: 286, opacity: 1, clashing: true }; break;
      case 9: key2 = { x: 150, y: 150, opacity: 0, clashing: false }; break;
      case 10:
      case 11:
      case 12:
        key1 = { x: 50, y: 286, opacity: 1, clashing: false };
        key2 = { x: 150, y: 286, opacity: 1, clashing: false };
        break;
    }
  } else {
    switch (phase) {
      case 1: wrongKey = { x: 100, y: 286, opacity: 1, clashing: false }; break;
      case 2: wrongKey = { x: 100, y: 286, opacity: 1, clashing: true }; break;
      case 3: wrongKey = { x: 100, y: 150, opacity: 0, clashing: false }; break;
      case 4:
      case 5:
      case 6:
        key1 = { x: 100, y: 286, opacity: 1, clashing: false };
        break;
      case 7: key1 = { x: 100, y: 150, opacity: 0, clashing: false }; break;
      case 8:
      case 9:
      case 10:
        key2 = { x: 100, y: 286, opacity: 1, clashing: false };
        break;
    }
  }
  const showClash =
    gateType === "AND" ? phase === 2 || phase === 5 || phase === 8 : phase === 2;

  const riboOp = isUnlocked ? 1 : 0;
  const riboX = isTranslating ? 760 : 445;
  const outScale = isTranslating ? 1.6 : 0;
  const outY = isTranslating ? 180 : 280;

  return (
    <div className="w-full">
      <style>{`
        @keyframes tha-wiggle {
          0%,100% { transform: translate(0,0) rotate(0); }
          25% { transform: translate(-3px,0) rotate(-0.6deg); }
          50% { transform: translate(3px,0) rotate(0.6deg); }
          75% { transform: translate(-2px,0) rotate(-0.4deg); }
        }
        .tha-wiggle { animation: tha-wiggle 0.25s ease-in-out infinite; }
      `}</style>

      {/* HUD banner */}
      <div className="mb-3 flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-2.5">
        <div className="flex items-center gap-2 border-r border-border pr-3">
          <span className="h-2 w-2 animate-pulse rounded-full bg-mint" />
          <span className="font-mono text-[10px] font-bold tracking-widest text-mint">
            {gateLabel} · {gateType}
          </span>
        </div>
        <p className="flex-1 font-mono text-[11px] tracking-wide text-foreground">
          {activePhases[phase].text}
        </p>
        <button
          onClick={() => setPaused((p) => !p)}
          className="rounded-md border border-border bg-surface px-2 py-1 font-mono text-[10px] text-muted-foreground hover:text-foreground"
        >
          {paused ? "PLAY" : "PAUSE"}
        </button>
      </div>

      {/* Canvas */}
      <div className="relative w-full overflow-hidden rounded-xl border border-border bg-surface">
        <svg viewBox="0 0 850 400" className="block h-auto w-full">
          <defs>
            <linearGradient id="tha-strand" x1="50" y1="300" x2="850" y2="300" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="var(--border)" />
              <stop offset="30%" stopColor="var(--muted-foreground)" />
              <stop offset="70%" stopColor="var(--muted-foreground)" />
              <stop offset="100%" stopColor="var(--border)" />
            </linearGradient>
            <pattern id="tha-grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M 32 0 L 0 0 0 32" fill="none" stroke="var(--border)" strokeWidth="0.5" opacity="0.4" />
            </pattern>
          </defs>
          <rect width="850" height="400" fill="url(#tha-grid)" />

          <path
            d={pathD}
            stroke="url(#tha-strand)"
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
            style={{ transition: "all 2s cubic-bezier(0.34, 1.56, 0.64, 1)" }}
          />

          {/* Stem base-pairing */}
          <g
            style={{ opacity: isUnlocked ? 0 : 1, transition: "opacity 0.6s" }}
            stroke="var(--accent)"
            strokeWidth="1.5"
            strokeDasharray="2,4"
          >
            <line x1="260" y1="280" x2="300" y2="280" />
            <line x1="260" y1="250" x2="300" y2="250" />
            <line x1="260" y1="220" x2="300" y2="220" />
            <line x1="260" y1="190" x2="300" y2="190" />
            <line x1="260" y1="160" x2="300" y2="160" />
          </g>

          {/* RBS */}
          <g
            style={{
              transform: `translate(${rbsPos.x}px, ${rbsPos.y}px)`,
              transition: "all 2s cubic-bezier(0.34, 1.56, 0.64, 1)",
            }}
          >
            <circle cx="0" cy="0" r="8" fill="oklch(0.78 0.14 90)" />
            <circle cx="0" cy="0" r="3" fill="#fff" opacity="0.9" />
            <text x="0" y="-14" fill="oklch(0.55 0.14 90)" fontSize="8" fontFamily="ui-monospace, monospace" fontWeight="bold" textAnchor="middle">
              RBS
            </text>
          </g>

          {/* Start codon */}
          <g
            style={{
              transform: `translate(${startPos.x}px, ${startPos.y}px)`,
              transition: "all 2s cubic-bezier(0.34, 1.56, 0.64, 1)",
            }}
          >
            <polygon points="-7,-7 8,0 -7,7" fill="oklch(0.65 0.18 145)" />
            <text x="0" y="-14" fill="oklch(0.5 0.18 145)" fontSize="8" fontFamily="ui-monospace, monospace" fontWeight="bold" textAnchor="middle">
              START
            </text>
          </g>

          {/* Toehold pad */}
          <line x1="50" y1="300" x2="250" y2="300" stroke="var(--mint)" strokeWidth="10" strokeLinecap="round" opacity="0.12" />
          <line x1="50" y1="308" x2="250" y2="308" stroke="var(--mint)" strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />
          <text x="150" y="322" fill="var(--mint)" fontSize="8" fontFamily="ui-monospace, monospace" fontWeight="bold" textAnchor="middle" letterSpacing="2">
            TOEHOLD_DOMAIN
          </text>

          <text
            x="750"
            y="322"
            fill="var(--muted-foreground)"
            fontSize="8"
            fontFamily="ui-monospace, monospace"
            fontWeight="bold"
            textAnchor="middle"
            letterSpacing="2"
            style={{ transition: "opacity 2s", opacity: isUnlocked ? 1 : 0 }}
          >
            {output.name.toUpperCase()}_CDS
          </text>

          {/* Clash */}
          <g
            style={{
              opacity: showClash ? 1 : 0,
              transform: `translate(150px, 300px) scale(${showClash ? 1 : 0.8})`,
              transition: "all 0.2s ease",
            }}
          >
            <rect x="-20" y="-9" width="40" height="18" rx="4" fill="var(--accent)" stroke="var(--accent)" strokeWidth="1" />
            <text x="0" y="4" fill="var(--accent-foreground)" fontSize="9" fontFamily="ui-monospace, monospace" fontWeight="bold" textAnchor="middle">
              FAIL
            </text>
          </g>

          {/* Keys */}
          <RNAKey color="var(--accent)" name="Off-Target" x={wrongKey.x} y={wrongKey.y} opacity={wrongKey.opacity} clashing={wrongKey.clashing} />
          <RNAKey color={keys[0].color} name={keys[0].name} x={key1.x} y={key1.y} opacity={key1.opacity} clashing={key1.clashing} />
          <RNAKey color={keys[1].color} name={keys[1].name} x={key2.x} y={key2.y} opacity={key2.opacity} clashing={key2.clashing} />

          {/* Ribosome */}
          <g
            style={{
              transform: `translate(${riboX}px, 300px)`,
              opacity: riboOp,
              transition: `transform ${isTranslating ? 5 / playbackSpeed : 1.5 / playbackSpeed}s linear, opacity 0.8s`,
            }}
          >
            <path
              d="M -45 -8 L -35 -35 L 35 -35 L 45 -8 C 45 5, -45 5, -45 -8"
              fill="var(--deep-blue)"
              stroke="var(--border)"
              strokeWidth="1"
            />
            <path
              d="M -30 8 C -30 25, 30 25, 30 8 C 30 -2, -30 -2, -30 8"
              fill="var(--primary)"
              stroke="var(--border)"
              strokeWidth="1"
            />
            <circle cx="0" cy="0" r="4" fill="var(--mint)" opacity={isTranslating ? 1 : 0.4} />
            <text
              x="0"
              y="-42"
              fill="var(--muted-foreground)"
              fontSize="8"
              fontFamily="ui-monospace, monospace"
              fontWeight="bold"
              textAnchor="middle"
            >
              RIBOSOME
            </text>
          </g>

          {/* Output protein */}
          <g
            style={{
              transform: `translate(${riboX}px, ${outY}px) scale(${outScale})`,
              opacity: outScale > 0 ? 1 : 0,
              transition: `transform ${isTranslating ? 5 / playbackSpeed : 0.5 / playbackSpeed}s linear, opacity 0.8s`,
            }}
          >
            <polygon points="0,-14 12,-6 12,8 0,16 -12,8 -12,-6" fill={output.color} />
            <circle cx="0" cy="1" r="3" fill="#ffffff" opacity="0.75" />
            <text
              x="0"
              y="-20"
              fill={output.color}
              fontSize="8"
              fontFamily="ui-monospace, monospace"
              fontWeight="bold"
              textAnchor="middle"
            >
              {output.name}
            </text>
          </g>
        </svg>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2 text-[10px] font-mono text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-mint" /> {keys[0].name}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm" style={{ background: "var(--deep-blue)" }} /> {keys[1].name}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm" style={{ background: output.color }} /> Output · {output.name}
        </div>
      </div>
    </div>
  );
}


function PlasmidRing({ candidate }: { candidate: Candidate }) {
  const cc = candidate.ringColors;
  const features = [
    { start: 10, end: 80, color: cc.promoter, label: "Promoter" },
    { start: 90, end: 160, color: cc.switch, label: "Switch" },
    { start: 170, end: 240, color: cc.payload, label: "GFP" },
    { start: 250, end: 310, color: cc.marker, label: "AmpR" },
    { start: 320, end: 355, color: cc.term, label: "Term" },
  ];
  const r = 100;
  const cx = 130;
  const cy = 130;
  const polar = (deg: number) => {
    const a = ((deg - 90) * Math.PI) / 180;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };
  const arc = (start: number, end: number) => {
    const [x1, y1] = polar(start);
    const [x2, y2] = polar(end);
    const large = end - start > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
  };
  return (
    <svg width="260" height="260" viewBox="0 0 260 260" className="drop-shadow-sm">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border)" strokeWidth="1" strokeDasharray="2 4" />
      <circle cx={cx} cy={cy} r={r - 14} fill="none" stroke="var(--border)" strokeWidth="1" />
      {features.map((f, i) => (
        <path
          key={i}
          d={arc(f.start, f.end)}
          stroke={f.color}
          strokeWidth="10"
          fill="none"
          strokeLinecap="round"
        />
      ))}
      {Array.from({ length: 24 }).map((_, i) => {
        const [x1, y1] = polar(i * 15);
        const a = ((i * 15 - 90) * Math.PI) / 180;
        const x2 = cx + (r + 8) * Math.cos(a);
        const y2 = cy + (r + 8) * Math.sin(a);
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--muted-foreground)" strokeWidth="0.5" opacity="0.4" />;
      })}
      <text x={cx} y={cy - 6} textAnchor="middle" className="fill-foreground font-mono" fontSize="11" fontWeight="600">
        {candidate.name}
      </text>
      <text x={cx} y={cy + 10} textAnchor="middle" className="fill-muted-foreground font-mono" fontSize="9">
        {candidate.bp.toLocaleString()} bp
      </text>
      <text x={cx} y={cy + 24} textAnchor="middle" className="fill-mint font-mono" fontSize="9">
        ● optimized
      </text>
    </svg>
  );
}

/* ---------- Page ---------- */
function Index() {
  return (
    <div className="min-h-screen bg-background">
      <Nav />

      {/* Page header */}
      <div className="border-b border-border bg-surface/60">
        <div className="mx-auto max-w-[1400px] px-8 py-8">
          <div className="flex items-end justify-between gap-6">
            <div>
              <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                <LayoutDashboard className="h-3 w-3" />
                Dashboard / New Circuit
              </div>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-foreground">
                Biological Compiler
                <span className="ml-2 font-mono text-base text-muted-foreground">v2.4</span>
              </h1>
              <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                Translate transcriptomic signals into manufacturable genetic circuits.
                Inputs → Logic → Payload → Plasmid.
              </p>
            </div>
            <div className="hidden gap-2 lg:flex">
              <button className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm text-foreground hover:border-mint">
                <Library className="h-4 w-4" /> My Circuits
              </button>
              <button className="inline-flex items-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background hover:opacity-90">
                <CircuitBoard className="h-4 w-4" /> Compile & Optimize
              </button>
            </div>
          </div>

          <div className="mt-6">
            <StepRail active={3} />
          </div>
        </div>
      </div>

      {/* Main content */}
      <main className="mx-auto max-w-[1400px] space-y-6 px-8 py-10">
        <Step1 />
        <Step2 />
        <Step3 />
        <Step4 />
        <CircuitExplanation />

        <footer className="flex items-center justify-between border-t border-border pt-6 font-mono text-[11px] text-muted-foreground">
          <div>CERNAL · Synthetic Biology Compiler · © 2026</div>
          <div className="flex items-center gap-4">
            <span>v2.4.1</span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-mint" /> All systems operational
            </span>
          </div>
        </footer>
      </main>
    </div>
  );
}
