/**
 * The wizard steps, adapted from the Lovable design.
 *
 * The design's versions were decorative — fixed values, no state, nothing submitted.
 * These are controlled components over the shared `CompileConfig`.
 */

import { Activity, Dna, FileUp, Sparkles, UploadCloud } from "lucide-react";
import { useRef } from "react";

import type { Dataset, GateFamily } from "@/api/types";
import { BacteriaIcon, HumanIcon, YeastIcon } from "@/components/icons/BioIcons";
import { Panel, SectionHeading, AdvancedOptions } from "@/components/layout/Primitives";
import { Check, SliderRow, Token } from "@/components/compile/Bits";

/* ---------- shared config ---------- */

export type Organism = "ecoli" | "yeast" | "human";
export type InputModeValue = "de" | "direct";

export interface CompileConfig {
  organism: Organism;
  inputMode: InputModeValue;
  datasetId: string | null;
  triggerSequence: string;
  setA: string;
  setB: string;
  mechanism: string;
  reporters: string[];
  markers: string[];
  customPayload: string;
  constraints: {
    max_leakage: number;
    min_mfe: number;
    min_off_target_score: number;
    max_length_bp: number;
    target_gc: number;
  };
}

export const DEFAULT_CONFIG: CompileConfig = {
  organism: "ecoli",
  inputMode: "de",
  datasetId: null,
  triggerSequence: "",
  setA: "",
  setB: "",
  mechanism: "toehold",
  reporters: ["gfp"],
  markers: ["ampr"],
  customPayload: "",
  constraints: {
    max_leakage: 0.08,
    min_mfe: -32,
    min_off_target_score: 85,
    max_length_bp: 5000,
    target_gc: 50,
  },
};

const ORGANISMS = [
  { key: "ecoli", label: "E. coli", Icon: BacteriaIcon, anim: "animate-bacteria" },
  { key: "yeast", label: "Yeast", Icon: YeastIcon, anim: "animate-yeast" },
  { key: "human", label: "Human", Icon: HumanIcon, anim: "animate-human" },
] as const;

const sanitizeRna = (v: string) => v.toUpperCase().replace(/[^ACGUT]/g, "").replace(/T/g, "U");

type Patch = (patch: Partial<CompileConfig>) => void;

/* ---------- Step 1 · Inputs ---------- */

export function StepInputs({
  config,
  patch,
  datasets,
  uploading,
  uploadError,
  onUpload,
}: {
  config: CompileConfig;
  patch: Patch;
  datasets: Dataset[];
  uploading: boolean;
  uploadError: string | null;
  onUpload: (file: File) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const selected = datasets.find((d) => d.id === config.datasetId) ?? null;

  return (
    <Panel>
      <SectionHeading
        kicker="Step 01 · Inputs"
        title="Define Transcriptomic Inputs"
        desc="Upload your differential expression results, or skip discovery and provide the exact trigger mRNA sequence directly."
      />

      <div className="mb-6">
        <label className="mb-2 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          Organism System
        </label>
        <div className="inline-flex rounded-lg border border-border bg-surface p-1">
          {ORGANISMS.map((o) => (
            <button
              key={o.key}
              type="button"
              onClick={() => patch({ organism: o.key })}
              className={`group flex items-center gap-2 rounded-md px-5 py-2.5 text-sm transition ${
                config.organism === o.key
                  ? "bg-card font-medium text-foreground shadow-clinical"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <o.Icon className={`h-4 w-4 ${o.anim}`} />
              <span>{o.label}</span>
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
            type="button"
            onClick={() => patch({ inputMode: "de" })}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm transition ${
              config.inputMode === "de"
                ? "bg-card font-medium text-foreground shadow-clinical"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Activity className="h-3.5 w-3.5" />
            Differential Expression
          </button>
          <button
            type="button"
            onClick={() => patch({ inputMode: "direct" })}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm transition ${
              config.inputMode === "direct"
                ? "bg-card font-medium text-foreground shadow-clinical"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Dna className="h-3.5 w-3.5" />
            Direct Trigger mRNA
          </button>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          {config.inputMode === "de"
            ? "Upload your differential expression results — CERNAL assumes fold change is calculated as target / control."
            : "Skip discovery — provide the exact mRNA sequence you want to act as the trigger."}
        </p>
      </div>

      {config.inputMode === "de" ? (
        <div className="rounded-xl border-2 border-dashed border-border bg-surface p-6 transition hover:border-mint hover:bg-mint/5">
          <div className="flex items-start gap-4">
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-lg bg-gradient-mint shadow-mint">
              <UploadCloud className="h-5 w-5 text-mint-foreground" />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="text-base font-semibold text-foreground">
                Differential Expression Results
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                A fold-change column is required. Common exports are recognised
                automatically —{" "}
                <span className="font-mono text-foreground">log2FoldChange</span>,{" "}
                <span className="font-mono text-foreground">fold_change</span>,{" "}
                <span className="font-mono text-foreground">FC</span>.
              </p>

              <div className="mt-4 flex flex-wrap items-center gap-3">
                <input
                  ref={fileInput}
                  type="file"
                  accept=".csv,.tsv,.txt,.xlsx"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) onUpload(file);
                    e.target.value = "";
                  }}
                />
                <button
                  type="button"
                  disabled={uploading}
                  onClick={() => fileInput.current?.click()}
                  className="rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:border-mint disabled:opacity-60"
                >
                  <FileUp className="mr-1.5 inline h-3.5 w-3.5" />
                  {uploading ? "Uploading…" : "Browse files"}
                </button>
                <span className="font-mono text-xs text-muted-foreground">
                  .csv · .tsv · .xlsx · max 100MB
                </span>
              </div>

              {uploadError && (
                <p role="alert" className="mt-3 text-sm text-destructive">
                  {uploadError}
                </p>
              )}

              {datasets.length > 0 && (
                <div className="mt-4 space-y-2">
                  {datasets.map((dataset) => (
                    <DatasetRow
                      key={dataset.id}
                      dataset={dataset}
                      selected={dataset.id === config.datasetId}
                      onSelect={() => patch({ datasetId: dataset.id })}
                    />
                  ))}
                </div>
              )}

              {selected?.validation_status === "INVALID" && (
                <ValidationErrors dataset={selected} />
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border-2 border-dashed border-border bg-surface p-6">
          <div className="flex items-start gap-4">
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-lg bg-gradient-mint shadow-mint">
              <Dna className="h-5 w-5 text-mint-foreground" />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="text-base font-semibold text-foreground">Trigger mRNA Sequence</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Paste the mRNA transcript that should activate the riboswitch. DNA is
                accepted and converted automatically.
              </p>
              <textarea
                value={config.triggerSequence}
                onChange={(e) => patch({ triggerSequence: sanitizeRna(e.target.value) })}
                placeholder="AUGGCUAGCAAGGGCGAGGAGCUGUUC..."
                rows={5}
                className="mt-4 w-full rounded-md border border-border bg-card p-3 font-mono text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-mint focus:outline-none"
              />
              <div className="mt-2 flex items-center justify-between font-mono text-xs text-muted-foreground">
                <span>A · C · G · U only · at least 20 nt</span>
                <span
                  className={
                    config.triggerSequence.length > 0 && config.triggerSequence.length < 20
                      ? "text-destructive"
                      : ""
                  }
                >
                  {config.triggerSequence.length} nt
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}

function DatasetRow({
  dataset,
  selected,
  onSelect,
}: {
  dataset: Dataset;
  selected: boolean;
  onSelect: () => void;
}) {
  const usable = dataset.validation_status === "VALID";
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={!usable}
      className={`flex w-full items-center gap-3 rounded-lg border p-3 text-left transition ${
        selected ? "border-mint bg-mint/5" : "border-border bg-card hover:border-mint/40"
      } ${usable ? "" : "opacity-70"}`}
    >
      <Check on={selected} />
      <div className="min-w-0 flex-1">
        <div className="truncate font-mono text-xs text-foreground">{dataset.name}</div>
        <div className="text-[11px] text-muted-foreground">
          {dataset.validation_report?.rows ?? 0} rows · {(dataset.size_bytes / 1024).toFixed(0)} KB
        </div>
      </div>
      <span
        className={`rounded-md px-2 py-0.5 font-mono text-[10px] ${
          usable ? "bg-mint/10 text-mint" : "bg-destructive/10 text-destructive"
        }`}
      >
        {dataset.validation_status}
      </span>
    </button>
  );
}

function ValidationErrors({ dataset }: { dataset: Dataset }) {
  return (
    <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3">
      <div className="font-mono text-[11px] uppercase tracking-wider text-destructive">
        This file cannot be analysed
      </div>
      <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-foreground">
        {dataset.validation_report.errors.map((error) => (
          <li key={error}>{error}</li>
        ))}
      </ul>
    </div>
  );
}

/* ---------- Step 2 · Logic ---------- */

export function StepLogic({
  config,
  patch,
  families,
}: {
  config: CompileConfig;
  patch: Patch;
  families: GateFamily[];
}) {
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
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              Set A · must be present
            </span>
            <input
              value={config.setA}
              onChange={(e) => patch({ setA: e.target.value })}
              placeholder="IL6, TNF, HIF1A"
              className="w-full rounded-md border border-border bg-card px-3 py-2 font-mono text-xs text-foreground focus:border-mint focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              Set B · must be absent
            </span>
            <input
              value={config.setB}
              onChange={(e) => patch({ setB: e.target.value })}
              placeholder="FOXP3"
              className="w-full rounded-md border border-border bg-card px-3 py-2 font-mono text-xs text-foreground focus:border-mint focus:outline-none"
            />
          </label>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Comma-separated gene identifiers. Leave blank to let the engine choose triggers
          from your data.
        </p>
      </div>

      <div className="mt-6">
        <div className="mb-3 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          Core Switch Mechanism
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {families.map((family) => {
            const active = config.mechanism === family.name;
            return (
              <button
                key={family.name}
                type="button"
                disabled={!family.available}
                onClick={() => patch({ mechanism: family.name })}
                title={family.available ? undefined : "Not implemented yet"}
                className={`flex items-start gap-3 rounded-xl border p-4 text-left transition ${
                  active
                    ? "border-mint bg-mint/5 shadow-mint"
                    : "border-border bg-surface hover:border-mint/50"
                } ${family.available ? "" : "cursor-not-allowed opacity-50 hover:border-border"}`}
              >
                <div
                  className={`mt-1 grid h-4 w-4 shrink-0 place-items-center rounded-full border-2 ${
                    active ? "border-mint" : "border-muted-foreground/40"
                  }`}
                >
                  {active && <div className="h-1.5 w-1.5 rounded-full bg-mint" />}
                </div>
                <div>
                  <div className="text-sm font-semibold text-foreground">{family.label}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{family.description}</div>
                  {!family.available && (
                    <div className="mt-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                      Coming soon
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <AdvancedOptions>
        <div className="grid gap-4 md:grid-cols-3">
          <SliderRow
            label="Off-State Leakage Limit"
            value={config.constraints.max_leakage}
            min={0}
            max={1}
            step={0.01}
            onChange={(v) =>
              patch({ constraints: { ...config.constraints, max_leakage: v } })
            }
          />
          <SliderRow
            label="Folding Energy (MFE) Min"
            value={config.constraints.min_mfe}
            min={-60}
            max={0}
            unit=" kcal/mol"
            onChange={(v) => patch({ constraints: { ...config.constraints, min_mfe: v } })}
          />
          <SliderRow
            label="Off-Target Screening"
            value={config.constraints.min_off_target_score}
            min={0}
            max={100}
            unit="%"
            onChange={(v) =>
              patch({ constraints: { ...config.constraints, min_off_target_score: v } })
            }
          />
        </div>
      </AdvancedOptions>
    </Panel>
  );
}

/* ---------- Step 3 · Payload ---------- */

const REPORTERS = [
  { key: "gfp", name: "GFP", sub: "Green Fluorescent Protein", color: "oklch(0.82 0.18 145)" },
  { key: "mcherry", name: "mCherry", sub: "Red Fluorescent Protein", color: "oklch(0.65 0.22 25)" },
  { key: "luciferase", name: "Luciferase", sub: "Bioluminescent readout", color: "oklch(0.85 0.16 90)" },
];

const MARKERS = [
  { key: "ampr", name: "Antibiotic Resistance", sub: "AmpR · KanR positive selection", kind: "Positive" },
  { key: "apoptosis", name: "Apoptosis Inducer", sub: "Programmed cell death kill-switch", kind: "Negative" },
];

export function StepPayload({ config, patch }: { config: CompileConfig; patch: Patch }) {
  const toggle = (list: string[], key: string) =>
    list.includes(key) ? list.filter((k) => k !== key) : [...list, key];

  return (
    <Panel>
      <SectionHeading
        kicker="Step 03 · Payload"
        title="Choose Downstream Output"
        desc="Select the downstream output module — visual reporters for validation, functional selective markers for phenotype gating, or your own mRNA sequence."
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
            {REPORTERS.map((r) => {
              const on = config.reporters.includes(r.key);
              return (
                <button
                  key={r.key}
                  type="button"
                  onClick={() => patch({ reporters: toggle(config.reporters, r.key) })}
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
          <div className="mb-3 font-mono text-[11px] uppercase tracking-wider text-foreground">
            Selective Markers · Phenotype Gating
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {MARKERS.map((m) => {
              const on = config.markers.includes(m.key);
              return (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => patch({ markers: toggle(config.markers, m.key) })}
                  className={`flex items-start justify-between gap-4 rounded-xl border p-5 text-left transition ${
                    on ? "border-mint bg-mint/5" : "border-border bg-surface hover:border-mint/40"
                  }`}
                >
                  <div>
                    <div className="text-sm font-semibold text-foreground">{m.name}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{m.sub}</div>
                    <div className="mt-2 inline-block rounded-md bg-secondary px-2 py-0.5 font-mono text-[10px] tracking-wider text-muted-foreground">
                      {m.kind} selection
                    </div>
                  </div>
                  <Check on={on} />
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <div className="mb-3 font-mono text-[11px] uppercase tracking-wider text-foreground">
            Custom Output · Your Own mRNA
          </div>
          <textarea
            value={config.customPayload}
            onChange={(e) =>
              patch({ customPayload: e.target.value.toUpperCase().replace(/[^ACGU]/g, "") })
            }
            placeholder="Optional — paste a coding sequence to express instead of a reporter"
            rows={3}
            className="w-full rounded-md border border-border bg-surface p-3 font-mono text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-mint focus:outline-none"
          />
        </div>
      </div>
    </Panel>
  );
}
