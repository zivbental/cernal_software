/**
 * The two input genes of a two-input AND gate, picked from the dataset chosen in step 1.
 *
 * The AND needs a differential-expression table to name its inputs, so this reads the same
 * ranked preview the dataset already has (`useDatasetPreview`). Only up-regulated genes are
 * offered: the gate is activated by its inputs, and a down-regulated gene cannot be one. The
 * eukaryotic gate permits two windows of the same gene. The bacterial gate searches
 * the upstream gene pool by default, or accepts an optional pair of different genes.
 */

import { useDatasetPreview } from "@/api/queries";
import type { DatasetPreviewRow } from "@/api/types";

export interface AndGenes {
  a: string;
  b: string;
}

function label(row: DatasetPreviewRow) {
  const fold = row.log2fc === null ? "" : ` · log2FC ${row.log2fc.toFixed(2)}`;
  return `${row.gene_symbol || row.gene_id}${row.gene_symbol ? ` (${row.gene_id})` : ""}${fold}`;
}

export function AndInputs({
  datasetId,
  value,
  onChange,
  bacterial = false,
}: {
  datasetId: string | null;
  value: AndGenes;
  onChange: (next: AndGenes) => void;
  bacterial?: boolean;
}) {
  const preview = useDatasetPreview(datasetId);
  const rows = (preview.data?.rows ?? []).filter((row) => row.log2fc !== null && row.log2fc > 0);

  if (!datasetId) {
    return (
      <p className="mt-4 text-sm text-muted-foreground">
        Choose a dataset in step 1, then pick the two input genes here.
      </p>
    );
  }
  if (preview.isLoading) return <p className="mt-4 text-sm text-muted-foreground">Loading genes…</p>;
  if (preview.isError)
    return (
      <p role="alert" className="mt-4 text-sm text-destructive">
        Could not read the genes of this dataset.
      </p>
    );

  const field = (id: string, title: string, key: keyof AndGenes) => (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-xs text-foreground">
        {title}
      </label>
      <select
        id={id}
        value={value[key]}
        onChange={(event) => onChange({ ...value, [key]: event.target.value })}
        className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm"
      >
        <option value="">{bacterial ? "Automatic selection from the dataset" : "Choose a gene…"}</option>
        {rows.map((row) => (
          <option key={row.gene_id} value={row.gene_id}>
            {label(row)}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="mt-6" data-testid="and-inputs">
      <div className="mb-3 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
        {bacterial ? "Optional input gene pair" : "Two Input Genes"}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {field("and-gene-a", bacterial ? "First input gene" : "Input A (5′ hairpin)", "a")}
        {field("and-gene-b", bacterial ? "Second input gene" : "Input B (3′ hairpin)", "b")}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        The payload is intended to be made only when both genes are expressed. Both come from the
        dataset above and must be up-regulated. {bacterial
          ? "Leave both selectors empty to search CERNAL's selected gene pool, or choose two different genes. Accessible regions focus overlap discovery; complete AND trigger footprints are then scored with CERNAL's accessibility method. Folding includes the switch through its linker and excludes the output CDS."
          : "Choose the same gene twice to use two windows of one transcript."}{" "}
        {preview.data?.truncated ? "Showing the top-ranked genes of a large table." : ""}
        {rows.length === 0 ? " This dataset has no up-regulated genes to choose from." : ""}
      </p>
    </div>
  );
}
