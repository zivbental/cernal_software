import { useMemo, useState } from "react";
import { RotateCcw, RotateCw, ZoomIn, ZoomOut } from "lucide-react";

import { useCandidateStructure } from "@/api/queries";
import type { CandidateDetail, CandidateStructure } from "@/api/types";
import { getGateRegions, getPrimarySwitchNotice, getStructureProvenanceLabel } from "@/lib/rna-structure";
import { BASE_COLORS, RnaDrawing } from "@/vendor/cernal-rnaviz/drawing";

/** A persisted record or API response may predate the current data contract. */
function drawable(data: CandidateStructure, candidate: CandidateDetail) {
  if (typeof data.sequence !== "string" || !/^[ACGU]+$/.test(data.sequence)
    || typeof data.structure !== "string" || data.structure.length !== data.sequence.length
    || data.sequence !== candidate.design.switch_sequence || data.structure !== candidate.design.structure
    || !Array.isArray(data.bases) || data.bases.length !== data.sequence.length
    || !Array.isArray(data.links)) return false;
  if (!data.bases.every((base, index) => base && base.index === index && base.char === data.sequence[index]
    && Number.isFinite(base.x) && Number.isFinite(base.y))) return false;
  const stack: number[] = [];
  const expected = new Set<string>();
  for (let index = 0; index < data.structure.length; index++) {
    const symbol = data.structure[index];
    if (symbol === "(") stack.push(index);
    else if (symbol === ")") {
      const source = stack.pop();
      if (source === undefined) return false;
      expected.add(`${source}:${index}`);
    } else if (symbol !== ".") return false;
  }
  if (stack.length || data.links.length !== expected.size) return false;
  const actual = new Set(data.links.map((link) => link && `${link.source}:${link.target}`));
  return actual.size === expected.size && [...actual].every((pair) => expected.has(pair));
}

/** Only mounted for the selected candidate. Its key resets controls on selection. */
export function RnaStructureView({ candidate }: { candidate: CandidateDetail }) {
  const query = useCandidateStructure(candidate.id);
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const annotations = useMemo(() => getGateRegions(
    candidate.gate_family, candidate.design.switch_sequence, candidate.design.architecture,
  ), [candidate.gate_family, candidate.design.switch_sequence, candidate.design.architecture]);
  const primaryNotice = getPrimarySwitchNotice(candidate.design.component_switches);
  const title = getStructureProvenanceLabel(candidate.design.structure_kind);
  const buttonClass = "inline-flex items-center gap-1 rounded-md border border-border px-2 py-1.5 text-xs hover:bg-secondary disabled:opacity-40";

  if (query.isPending) return <p role="status" className="py-12 text-center text-sm text-muted-foreground">Loading saved RNA structure…</p>;
  if (query.isError) return <div role="alert" className="rounded-lg border border-border p-5 text-sm">
    Could not load the RNA structure. Your other results are still available.
    <button className={`${buttonClass} ml-2`} onClick={() => query.refetch()}>Retry structure</button>
  </div>;
  const data = query.data;
  if (!data || typeof data !== "object" || !["available", "unavailable", "invalid", "error"].includes(data.status)) {
    return <p role="alert" className="rounded-lg border border-border p-5 text-sm">The server returned invalid RNA drawing data. No diagram is shown.</p>;
  }
  if (data.status !== "available") return <div role={data.status === "invalid" || data.status === "error" ? "alert" : "status"}
    className="rounded-xl border border-dashed border-border p-6 text-sm">
    <p className="font-medium">{data.status === "invalid" ? "Saved RNA structure is invalid" : data.status === "error" ? "RNA drawing could not be generated" : "RNA structure unavailable"}</p>
    <p className="mt-2 text-muted-foreground">{data.reason || "No drawable structure was saved for this candidate."}</p>
    <p className="mt-2 text-muted-foreground">A missing structure is not evidence that the RNA is unpaired.</p>
    {data.status === "error" && <button className={`${buttonClass} mt-3`} onClick={() => query.refetch()}>Retry structure</button>}
  </div>;
  if (!drawable(data, candidate)) return <p role="alert" className="rounded-lg border border-border p-5 text-sm">
    The drawing data does not match this candidate’s saved sequence and structure. No diagram is shown.
  </p>;

  const selectedBase = selected === null ? null : data.bases[selected];
  const selectedRegion = selected === null ? null : annotations.regions.find((region) => selected >= region.start && selected < region.end);
  const paired = selected === null ? null : data.links.find((link) => link.source === selected || link.target === selected);
  const partner = paired ? (paired.source === selected ? paired.target : paired.source) : null;
  const triggerLabels = Array.isArray(candidate.triggers?.features) ? candidate.triggers.features.flatMap((feature) => {
    if (!feature || typeof feature !== "object") return [];
    const name = feature.gene_symbol || feature.gene_id;
    return typeof name === "string" && name ? [name] : [];
  }) : [];

  return <section aria-label="Candidate RNA structure" className="w-full min-w-0">
    <h3 className="text-sm font-semibold">{title}</h3>
    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
      {candidate.design.structure_kind === "intended_target"
        ? "The designed pairing pattern for the saved switch. This is not a predicted OFF/ON fold or experimental evidence."
        : "Pairing as saved with this candidate. Its provenance is unspecified; no predicted OFF/ON state is inferred."}
    </p>
    {primaryNotice && <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">{primaryNotice}</p>}
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
      <span className="font-mono text-[11px] text-muted-foreground">{data.sequence.length} nt · {data.links.length} base pairs</span>
      <div role="group" aria-label="RNA drawing controls" className="flex flex-wrap gap-1">
        <button className={buttonClass} aria-label="Zoom out RNA" disabled={zoom <= 0.5} onClick={() => setZoom((value) => Math.max(0.5, value / 1.25))}><ZoomOut className="h-3.5 w-3.5" /></button>
        <button className={buttonClass} onClick={() => { setZoom(1); setRotation(0); setSelected(null); }}>Reset view</button>
        <button className={buttonClass} aria-label="Zoom in RNA" disabled={zoom >= 4} onClick={() => setZoom((value) => Math.min(4, value * 1.25))}><ZoomIn className="h-3.5 w-3.5" /></button>
        <button className={buttonClass} aria-label="Rotate RNA left" onClick={() => setRotation((value) => (value + 270) % 360)}><RotateCcw className="h-3.5 w-3.5" /></button>
        <button className={buttonClass} aria-label="Rotate RNA right" onClick={() => setRotation((value) => (value + 90) % 360)}><RotateCw className="h-3.5 w-3.5" /></button>
      </div>
    </div>
    <div className="mt-3 h-[400px] w-full overflow-auto rounded-xl border border-slate-700 bg-slate-900 p-2" data-testid="rna-canvas">
      <RnaDrawing bases={data.bases} links={data.links} regions={annotations.regions}
        rotation={rotation} zoom={zoom} selected={selected} onSelect={setSelected}
        title={`${candidate.engine_ref}: ${title}`} />
    </div>
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground" aria-label="RNA drawing legend">
      {Object.entries(BASE_COLORS).map(([base, color]) => <span key={base} className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />{base}</span>)}
      <span>Solid: backbone</span><span>Dashed: stored base pair</span>
    </div>
    <p aria-live="polite" className="mt-3 min-h-9 text-xs leading-relaxed">
      {selectedBase ? <>{selectedBase.char} at position {selectedBase.index + 1}{selectedRegion ? ` · ${selectedRegion.label}` : ""}{partner !== null ? ` · paired with ${data.sequence[partner]} at ${partner + 1}` : " · unpaired in this structure"}</> : "Select a nucleotide to inspect it. Use arrow keys to move along the sequence."}
    </p>
    {annotations.regions.length > 0 && <div className="flex flex-wrap gap-2" aria-label="RNA regions">
      {annotations.regions.map((region) => <button key={`${region.start}-${region.end}`} className={`${buttonClass} text-left`}
        onClick={() => setSelected(region.start)} title={`${region.label}: positions ${region.start + 1}–${region.end}`}>
        <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: region.color }} />
        {region.label} <span className="text-muted-foreground">{region.start + 1}–{region.end}</span>
      </button>)}
    </div>}
    {annotations.notice && <p className="mt-2 text-xs text-muted-foreground">{annotations.notice}</p>}
    {triggerLabels.length > 0 && <p className="mt-3 text-xs text-muted-foreground">Input{triggerLabels.length === 1 ? "" : "s"}: {[...new Set(triggerLabels)].join(", ")}. Trigger-bound pairing is not part of this saved drawing.</p>}
    <details className="mt-3 text-xs"><summary className="cursor-pointer text-muted-foreground">Stored dot-bracket structure</summary><pre className="mt-2 whitespace-pre-wrap break-all font-mono">{data.structure}</pre></details>
    <p className="mt-3 text-[10px] text-muted-foreground">Visualization adapted from cernal-rnaviz · local stored-structure layout · positions are 1-based</p>
  </section>;
}
