/** Plain nucleotides or one FASTA record. Coordinates never lose invalid bases. */
export function parseSequence(text: string): { sequence: string; error: string | null } {
  const lines = text.trim().split(/\r?\n/);
  const headers = lines.filter((line) => line.trim().startsWith(">"));
  if (headers.length > 1) return { sequence: "", error: "Paste one FASTA record at a time." };
  if (headers.length && !lines[0].trim().startsWith(">"))
    return { sequence: "", error: "A FASTA header must be the first line." };
  const body = (headers.length ? lines.slice(1) : lines).join("\n");
  const sequence = body.replace(/\s/g, "").toUpperCase().replace(/T/g, "U");
  const invalid = sequence.search(/[^ACGU]/);
  if (invalid >= 0) return { sequence, error: `Invalid nucleotide '${sequence[invalid]}' at position ${invalid + 1}. Use A, C, G, U or T; ambiguity is unsupported.` };
  if (headers.length && !sequence) return { sequence, error: "The FASTA record has no sequence." };
  return { sequence, error: null };
}
