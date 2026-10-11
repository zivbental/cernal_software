/** A named interval in the stored switch sequence, using zero-based [start, end). */
export interface GateRegion {
  label: string;
  start: number;
  end: number;
  color: string;
}

interface GateRegions {
  regions: GateRegion[];
  notice: string | null;
}

const SINGLE_INPUT_TOEHOLDS = new Set([
  "toehold",
  "prokaryotic_toehold",
  "eukaryotic_toehold",
]);

const COLORS = {
  toehold: "#0891b2",
  stem: "#7c3aed",
  loop: "#d97706",
  kozak: "#2563eb",
  aug: "#dc2626",
  linker: "#64748b",
  payload: "#059669",
};

// Sequence motifs used by ToeholdGate in src/engine/gates/toehold.py. These are
// checked only to label stored regions; this adapter does not predict a fold.
const RBS = "AACAGAGGAGA";
const KOZAK = "GCCACC";
const BULGE_LENGTH = 3;

function withoutRegions(reason: string): GateRegions {
  return { regions: [], notice: `Region annotations unavailable: ${reason}` };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readLength(
  architecture: Record<string, unknown>,
  key: string,
  sequenceLength: number,
): number | null {
  const value = architecture[key];
  return typeof value === "number" &&
    Number.isSafeInteger(value) &&
    value >= 0 &&
    value <= sequenceLength
    ? value
    : null;
}

/**
 * Map the serialized single-input ToeholdGate construction to the exact sequence.
 *
 * Missing/inconsistent metadata hides annotations, never the underlying structure.
 * Do not infer offsets from motifs, normalize the sequence, or apply this layout to
 * the separately constructed *_and families. The engine's loop/trailing builders
 * are the source of these coordinates, including the leader and payload-head tail.
 */
export function getGateRegions(
  gateFamily: string,
  sequence: unknown,
  architecture: unknown,
): GateRegions {
  if (!SINGLE_INPUT_TOEHOLDS.has(gateFamily)) {
    return withoutRegions("this gate family has no supported region map.");
  }
  // Persisted candidate metadata is read before the structure endpoint responds.
  // Guard it here as well, without coercing or normalizing away any coordinates.
  if (typeof sequence !== "string" || sequence.length === 0 || /[^ACGU]/.test(sequence)) {
    return withoutRegions("the stored switch sequence is missing or is not canonical RNA.");
  }
  if (!isRecord(architecture)) {
    return withoutRegions("stored architecture metadata is missing or invalid.");
  }

  const leader = readLength(architecture, "leader_len", sequence.length);
  const toehold = readLength(architecture, "toehold_length", sequence.length);
  const pre = readLength(architecture, "stem_pre_bulge_len", sequence.length);
  const post = readLength(architecture, "stem_post_bulge_len", sequence.length);
  const loop = readLength(architecture, "loop_len", sequence.length);
  const tail = readLength(architecture, "linker_len", sequence.length);
  const payload = readLength(architecture, "payload_head_length", sequence.length);
  const aug = readLength(architecture, "aug_index", sequence.length);
  if (
    leader === null || toehold === null || pre === null || post === null ||
    loop === null || tail === null || payload === null || aug === null ||
    toehold === 0 || pre === 0 || post === 0 || loop === 0
  ) {
    return withoutRegions("stored region lengths or offsets are missing or invalid.");
  }

  const layout = architecture.kozak_layout;
  const track = architecture.track;
  if (
    (layout !== "loop" && layout !== "trailing") ||
    (track !== "prokaryotic" && track !== "eukaryotic") ||
    (gateFamily === "prokaryotic_toehold" && track !== "prokaryotic") ||
    (gateFamily === "eukaryotic_toehold" && track !== "eukaryotic") ||
    (layout === "trailing" && track !== "eukaryotic")
  ) {
    return withoutRegions("the stored initiation layout or host track is unsupported.");
  }

  const kozakLinker = layout === "trailing" || "kozak_linker_len" in architecture
    ? readLength(architecture, "kozak_linker_len", sequence.length)
    : 0;
  if (kozakLinker === null || (layout === "loop" && kozakLinker !== 0)) {
    return withoutRegions("the stored Kozak spacer length is missing or invalid.");
  }
  if ((payload !== 0 && payload !== tail) || (layout === "trailing" && payload !== tail)) {
    return withoutRegions("stored linker and payload-head lengths are inconsistent.");
  }

  const upPreStart = leader + toehold;
  const upPreEnd = upPreStart + pre;
  const upPostStart = upPreEnd + BULGE_LENGTH;
  const loopStart = upPostStart + post;
  const loopEnd = loopStart + loop;
  const downPostEnd = loopEnd + post;
  const downPreStart = downPostEnd + BULGE_LENGTH;
  const hairpinEnd = downPreStart + pre;
  const kozakStart = hairpinEnd + kozakLinker;
  const expectedAug = layout === "loop" ? downPostEnd : kozakStart + KOZAK.length;
  const tailStart = layout === "loop" ? hairpinEnd : expectedAug + 3;
  if (
    aug !== expectedAug ||
    tailStart + tail !== sequence.length ||
    sequence.slice(aug, aug + 3) !== "AUG"
  ) {
    return withoutRegions("stored boundaries or the AUG do not match this sequence.");
  }

  if (layout === "loop") {
    const motif = track === "prokaryotic" ? RBS : KOZAK;
    if (loop < motif.length || sequence.slice(loopEnd - motif.length, loopEnd) !== motif) {
      return withoutRegions("the stored initiation-loop motif does not match this sequence.");
    }
  } else if (sequence.slice(kozakStart, expectedAug) !== KOZAK) {
    return withoutRegions("the stored Kozak motif does not match this sequence.");
  }

  const regions: GateRegion[] = [];
  const add = (label: string, start: number, end: number, color: string) => {
    if (end > start) regions.push({ label, start, end, color });
  };
  add("Toehold", leader, upPreStart, COLORS.toehold);
  // Keep the two bulges outside paired stem intervals. Reuse one Stem legend
  // label/color across the four disjoint intervals rather than inventing domains.
  add("Stem", upPreStart, upPreEnd, COLORS.stem);
  add("Stem", upPostStart, loopStart, COLORS.stem);
  add(layout === "loop" ? "Initiation loop" : "Loop", loopStart, loopEnd, COLORS.loop);
  add("Stem", loopEnd, downPostEnd, COLORS.stem);
  if (layout === "loop") add("AUG", aug, aug + 3, COLORS.aug);
  add("Stem", downPreStart, hairpinEnd, COLORS.stem);
  if (layout === "trailing") {
    add("Linker", hairpinEnd, kozakStart, COLORS.linker);
    add("Kozak", kozakStart, aug, COLORS.kozak);
    add("AUG", aug, aug + 3, COLORS.aug);
  }
  add(payload > 0 ? "Payload head" : "Linker", tailStart, sequence.length,
    payload > 0 ? COLORS.payload : COLORS.linker);

  // Validate the complete result before returning any annotations. Never clip an
  // out-of-bounds interval or shift it onto a nearby matching motif.
  if (regions.some(({ start, end }) =>
    !Number.isSafeInteger(start) || !Number.isSafeInteger(end) ||
    start < 0 || end <= start || end > sequence.length)) {
    return withoutRegions("stored region boundaries fall outside this sequence.");
  }
  return { regions, notice: null };
}

export function getStructureProvenanceLabel(structureKind: unknown): string {
  return structureKind === "intended_target"
    ? "Intended target structure"
    : "Stored structure · provenance unspecified";
}

/** Component sequences do not carry component folds in the candidate contract. */
export function getPrimarySwitchNotice(componentSwitches: unknown): string | null {
  return Array.isArray(componentSwitches) && componentSwitches.length > 1
    ? "Showing the primary switch only. Structures for the other component switches are not stored."
    : null;
}
