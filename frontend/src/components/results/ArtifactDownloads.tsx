/**
 * Everything a run produced, organized for downloading — not one box per file.
 *
 * Replaces the old flat grid of one clickable box per artifact, which read as an
 * undifferentiated wall of 20+ identical-looking tiles once a run had more than a
 * couple of candidates. Three ways to leave with files, matching how a researcher
 * actually thinks about it: everything, one category (sequences, summary tables,
 * …), or a hand-picked set.
 */

import { useMemo, useState } from "react";
import {
  Archive,
  ChevronDown,
  CircleDot,
  Dna,
  Download,
  FileSpreadsheet,
  FileText,
  Image as ImageIcon,
} from "lucide-react";

import { artifactsZipUrl, useArtifacts } from "@/api/queries";
import type { Artifact, ArtifactCategory } from "@/api/types";
import { Check } from "@/components/compile/Bits";
import { Panel, SectionHeading } from "@/components/layout/Primitives";

const CATEGORY_META: Record<
  ArtifactCategory,
  { label: string; description: string; Icon: typeof Dna }
> = {
  summary: {
    label: "Summary",
    description: "Candidate tables and the run's own configuration.",
    Icon: FileSpreadsheet,
  },
  sequences: {
    label: "Gate & switch sequences",
    description: "One FASTA per accepted candidate's switch.",
    Icon: Dna,
  },
  plasmids: {
    label: "Plasmid sequences",
    description: "Full construct sequences, GenBank format.",
    Icon: CircleDot,
  },
  diagrams: {
    label: "Diagrams",
    description: "Structure and logic-circuit renderings.",
    Icon: ImageIcon,
  },
  reports: { label: "Reports", description: "Formatted PDF summaries.", Icon: FileText },
  other: { label: "Other files", description: "", Icon: Archive },
};

const CATEGORY_ORDER: ArtifactCategory[] = [
  "summary",
  "sequences",
  "plasmids",
  "diagrams",
  "reports",
  "other",
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function groupByCategory(artifacts: Artifact[]): Map<ArtifactCategory, Artifact[]> {
  const map = new Map<ArtifactCategory, Artifact[]>();
  for (const artifact of artifacts) {
    const list = map.get(artifact.category);
    if (list) list.push(artifact);
    else map.set(artifact.category, [artifact]);
  }
  return map;
}

export function ArtifactDownloads({ runId }: { runId: string }) {
  const artifacts = useArtifacts(runId);
  const [expanded, setExpanded] = useState<Set<ArtifactCategory>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const byCategory = useMemo(() => groupByCategory(artifacts.data ?? []), [artifacts.data]);
  const items = artifacts.data ?? [];

  if (items.length === 0) return null;

  const totalSize = items.reduce((sum, a) => sum + a.size_bytes, 0);

  function toggleExpanded(category: ArtifactCategory) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  }

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <Panel>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <SectionHeading
          kicker="Artifacts"
          title="Downloads"
          desc={`${items.length} file${items.length === 1 ? "" : "s"} generated, ${formatBytes(totalSize)} total.`}
        />
        <a
          href={artifactsZipUrl(runId)}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-gradient-deep px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-clinical transition hover:opacity-95"
        >
          <Archive className="h-4 w-4" />
          Download everything (.zip)
        </a>
      </div>

      {selected.size > 0 && (
        <div className="mb-4 flex items-center justify-between rounded-lg border border-mint/40 bg-mint/5 px-4 py-2.5">
          <span className="text-sm text-foreground">
            {selected.size} file{selected.size === 1 ? "" : "s"} selected
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSelected(new Set())}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Clear
            </button>
            <a
              href={artifactsZipUrl(runId, { ids: [...selected] })}
              className="inline-flex items-center gap-2 rounded-md border border-mint bg-mint/10 px-3 py-1.5 text-xs font-medium text-mint hover:bg-mint/20"
            >
              <Download className="h-3.5 w-3.5" />
              Download selected (.zip)
            </a>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {CATEGORY_ORDER.filter((category) => byCategory.has(category)).map((category) => {
          const files = byCategory.get(category) ?? [];
          const meta = CATEGORY_META[category];
          const isOpen = expanded.has(category);
          const size = files.reduce((sum, a) => sum + a.size_bytes, 0);

          return (
            <div
              key={category}
              className="overflow-hidden rounded-xl border border-border bg-surface"
            >
              <div className="flex items-center gap-2 px-4 py-3">
                <button
                  type="button"
                  onClick={() => toggleExpanded(category)}
                  className="flex flex-1 items-center gap-3 text-left"
                >
                  <meta.Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-foreground">{meta.label}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {files.length} file{files.length === 1 ? "" : "s"} · {formatBytes(size)}
                    </div>
                  </div>
                  <ChevronDown
                    className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${
                      isOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>
                <a
                  href={artifactsZipUrl(runId, { category })}
                  title={`Download "${meta.label}" as a .zip`}
                  className="shrink-0 rounded-md border border-border p-2 text-muted-foreground transition hover:border-mint hover:text-mint"
                >
                  <Download className="h-3.5 w-3.5" />
                </a>
              </div>

              {isOpen && (
                <div className="max-h-64 space-y-1 overflow-y-auto border-t border-border p-2">
                  {files.map((artifact) => (
                    <div
                      key={artifact.id}
                      className="flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-card"
                    >
                      <button
                        type="button"
                        onClick={() => toggleSelected(artifact.id)}
                        aria-label={`Select ${artifact.name}`}
                      >
                        <Check on={selected.has(artifact.id)} />
                      </button>
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-mono text-xs text-foreground">
                          {artifact.name}
                        </div>
                        <div className="truncate text-[11px] text-muted-foreground">
                          {artifact.label}
                        </div>
                      </div>
                      <div className="shrink-0 font-mono text-[11px] text-muted-foreground">
                        {formatBytes(artifact.size_bytes)}
                      </div>
                      <a
                        href={artifact.download_url}
                        title={`Download ${artifact.name}`}
                        className="shrink-0 text-muted-foreground transition hover:text-mint"
                      >
                        <Download className="h-3.5 w-3.5" />
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
