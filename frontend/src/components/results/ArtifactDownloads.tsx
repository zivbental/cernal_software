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

import { artifactsZipUrl, runSummaryPdfUrl, useArtifacts } from "@/api/queries";
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
  const availableItems = items.filter((artifact) => artifact.download_available === true);
  const allItemsAvailable = availableItems.length === items.length;
  const allZipUrl = allItemsAvailable
    ? artifactsZipUrl(runId)
    : artifactsZipUrl(runId, { availableOnly: true });

  if (artifacts.isLoading) return <p>Loading artifacts…</p>;
  if (artifacts.isError) return <p role="alert">Could not load artifacts. <button onClick={() => artifacts.refetch()}>Retry</button></p>;
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
          kicker="Run files"
          title="Downloads"
          desc={`${items.length} additional file${items.length === 1 ? "" : "s"} generated${items.length ? `, ${formatBytes(totalSize)} total` : ""}.`}
        />
        <div className="flex shrink-0 flex-wrap gap-2">
          <a
            href={runSummaryPdfUrl(runId)}
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground transition hover:border-mint"
          >
            <FileText className="h-4 w-4" /> Download PDF summary
          </a>
          {allZipUrl ? (
            <a
              href={allZipUrl}
              className="inline-flex items-center gap-2 rounded-lg bg-gradient-deep px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-clinical transition hover:opacity-95"
            >
              <Archive className="h-4 w-4" />
              {allItemsAvailable ? "Download ZIP (.zip)" : "Download available ZIP (.zip)"}
            </a>
          ) : (
            <span
              aria-disabled="true"
              className="inline-flex items-center gap-2 rounded-lg bg-muted px-4 py-2.5 text-sm font-semibold text-muted-foreground"
            >
              <Archive className="h-4 w-4" /> No files for ZIP
            </span>
          )}
        </div>
      </div>

      {items.some((artifact) => artifact.download_available !== true) && (
        <p role="status" className="mb-4 text-sm text-muted-foreground">
          Some artifacts are withheld pending sequence release approval. The ZIP includes all currently available files; held files stay excluded. Select individual files below to make a smaller archive.
        </p>
      )}
      <p className="mb-4 rounded-lg border border-border p-3 text-xs">
        Screening context: candidate screening covers only the saved switch sequence, not these files or the full construct.
        A downloadable artifact, completed run or ranking score does not establish screening clearance or authorize release.
        Screening evidence is not currently embedded in these exports; retain the applicable identity and provenance separately.
      </p>
      <details>
      <summary className="mb-4 cursor-pointer text-sm">Choose files and review release information</summary>

      {items.length === 0 && <p className="mb-4 text-sm text-muted-foreground">No additional run files are available. The PDF summary can still be downloaded above.</p>}

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
          const availableFiles = files.filter((artifact) => artifact.download_available === true);
          const allCategoryFilesAvailable = availableFiles.length === files.length;
          const categoryZipUrl = availableFiles.length === 0
            ? undefined
            : allCategoryFilesAvailable
              ? artifactsZipUrl(runId, { category })
              : artifactsZipUrl(runId, { category, availableOnly: true });
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
                  aria-expanded={isOpen}
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
                {categoryZipUrl ? (
                  <a
                    href={categoryZipUrl}
                    title={`Download available "${meta.label}" files as a .zip`}
                    aria-label={`Download available ${meta.label} files as a .zip`}
                    className="shrink-0 rounded-md border border-border p-2 text-muted-foreground transition hover:border-mint hover:text-mint"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </a>
                ) : (
                  <button
                    type="button"
                    disabled
                    title={`No downloadable files in ${meta.label}`}
                    aria-label={`No downloadable files in ${meta.label}`}
                    className="shrink-0 cursor-not-allowed rounded-md border border-border p-2 text-muted-foreground opacity-50"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </button>
                )}
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
                        disabled={artifact.download_available !== true}
                        aria-label={`Select ${artifact.name}`}
                      >
                        <Check on={selected.has(artifact.id)} />
                      </button>
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-mono text-xs text-foreground">
                          {artifact.name}
                        </div>
                        <div className="truncate text-[11px] text-muted-foreground">
                          {artifact.label}{artifact.download_available !== true ? " — withheld pending release approval" : ""}
                        </div>
                      </div>
                      <div className="shrink-0 font-mono text-[11px] text-muted-foreground">
                        {formatBytes(artifact.size_bytes)}
                      </div>
                      <a
                        href={artifact.download_available === true ? artifact.download_url : undefined}
                        aria-disabled={artifact.download_available !== true}
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
      </details>
    </Panel>
  );
}
