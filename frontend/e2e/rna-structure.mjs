/** Offline contracts for annotations on the exact stored switch sequence. */
import assert from "node:assert/strict";
import { build } from "esbuild";
import { rmSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = path.resolve(import.meta.dirname, "..");
const bundle = path.join(import.meta.dirname, ".rna-structure-bundle.mjs");
let checks = 0;

// Deterministic construction examples from the two builders in
// src/engine/gates/toehold.py. Coordinates below are explicit expected values,
// not recalculated with the adapter's formulas.
const loopSequence = [
  "GGG", "ACGUACGUACGU", "GCGAAUCGC", "UAC", "GCAUGC",
  "AACAGAGGAGA", "GCAUGC", "AUG", "GCGAUUCGC", "AACCUGGCGGCAGCGCAAAAG",
].join("");
const loopArchitecture = {
  leader_len: 3,
  toehold_length: 12,
  stem_pre_bulge_len: 9,
  stem_post_bulge_len: 6,
  loop_len: 11,
  linker_len: 21,
  payload_head_length: 0,
  aug_index: 50,
  kozak_layout: "loop",
  track: "prokaryotic",
};
const payload = "GCU".repeat(10);
const trailingSequence = [
  "GUCAGAUC", "ACGUACGUACGU", "GCGAAUCGC", "UAC", "GCAUGC",
  "ACAGACAGAC", "GCAUGC", "GUA", "GCGAUUCGC", "ACA", "GCCACC", "AUG", payload,
].join("");
const trailingArchitecture = {
  ...loopArchitecture,
  leader_len: 8,
  loop_len: 10,
  kozak_linker_len: 3,
  linker_len: 30,
  payload_head_length: 30,
  aug_index: 75,
  kozak_layout: "trailing",
  track: "eukaryotic",
};

function test(label, run) {
  run();
  checks += 1;
  console.log(`  ${label}: ok`);
}

function ranges(result) {
  assert.equal(result.notice, null);
  assert(result.regions.length > 0);
  return result.regions.map(({ label, start, end }) => [label, start, end]);
}

function unavailable(result) {
  assert.deepEqual(result.regions, []);
  assert.equal(typeof result.notice, "string");
  assert.match(result.notice, /Region annotations unavailable:/);
}

try {
  await build({
    entryPoints: [path.join(root, "src/lib/rna-structure.ts")],
    bundle: true,
    outfile: bundle,
    format: "esm",
    platform: "node",
    logLevel: "error",
  });
  const { getGateRegions, getStructureProvenanceLabel, getPrimarySwitchNotice } =
    await import(pathToFileURL(bundle).href);
  const loop = (architecture = loopArchitecture, sequence = loopSequence) =>
    getGateRegions("prokaryotic_toehold", sequence, architecture);
  const trailing = (architecture = trailingArchitecture, sequence = trailingSequence) =>
    getGateRegions("eukaryotic_toehold", sequence, architecture);

  test("loop layout keeps the nonzero leader and four exact paired stretches", () => {
    assert.equal(loopSequence.length, 83);
    assert.deepEqual(ranges(loop()), [
      ["Toehold", 3, 15], ["Stem", 15, 24], ["Stem", 27, 33],
      ["Initiation loop", 33, 44], ["Stem", 44, 50], ["AUG", 50, 53],
      ["Stem", 53, 62], ["Linker", 62, 83],
    ]);
    assert.equal(loopSequence.slice(50, 53), "AUG");
    assert.equal(loopSequence.slice(33, 44), "AACAGAGGAGA");
    assert.deepEqual(
      getGateRegions("toehold", loopSequence, loopArchitecture), loop(),
    );
  });

  test("trailing layout separates hairpin loop, spacer, Kozak, AUG and payload", () => {
    assert.equal(trailingSequence.length, 108);
    assert.deepEqual(ranges(trailing()), [
      ["Toehold", 8, 20], ["Stem", 20, 29], ["Stem", 32, 38],
      ["Loop", 38, 48], ["Stem", 48, 54], ["Stem", 57, 66],
      ["Linker", 66, 69], ["Kozak", 69, 75], ["AUG", 75, 78],
      ["Payload head", 78, 108],
    ]);
    assert(!trailing().regions.some(({ label }) => label === "Initiation loop"));
  });

  test("trailing layout permits zero spacer and no payload without empty regions", () => {
    const sequence = trailingSequence.slice(0, 66) + "GCCACCAUG";
    const result = trailing({
      ...trailingArchitecture, kozak_linker_len: 0, linker_len: 0,
      payload_head_length: 0, aug_index: 72,
    }, sequence);
    assert.deepEqual(ranges(result).slice(-2), [["Kozak", 66, 72], ["AUG", 72, 75]]);
    assert(!result.regions.some(({ label }) => ["Linker", "Payload head"].includes(label)));
  });

  test("loop layout labels the payload tail only after the descending stem", () => {
    const result = loop({ ...loopArchitecture, linker_len: 30, payload_head_length: 30 },
      loopSequence.slice(0, 62) + payload);
    assert.deepEqual(ranges(result).at(-1), ["Payload head", 62, 92]);
    assert.deepEqual(ranges(result).at(-2), ["Stem", 53, 62]);
    unavailable(loop({ ...loopArchitecture, payload_head_length: 19 }));
    unavailable(trailing({ ...trailingArchitecture, payload_head_length: 0 }));
  });

  test("eukaryotic loop uses its own leader and validates its Kozak motif", () => {
    const sequence = "GUCAGAUC" + loopSequence.slice(3, 33) + "ACAGAGCCACC" +
      loopSequence.slice(44);
    const architecture = { ...loopArchitecture, leader_len: 8, aug_index: 55, track: "eukaryotic" };
    const result = getGateRegions("eukaryotic_toehold", sequence, architecture);
    assert.deepEqual(ranges(result)[0], ["Toehold", 8, 20]);
    assert.deepEqual(ranges(result)[3], ["Initiation loop", 38, 49]);
    assert.deepEqual(ranges(result)[5], ["AUG", 55, 58]);
    unavailable(getGateRegions("prokaryotic_toehold", sequence, architecture));
    unavailable(getGateRegions("eukaryotic_toehold",
      sequence.slice(0, 43) + "A" + sequence.slice(44), architecture));
  });

  test("only exact supported family names receive labels", () => {
    for (const family of ["toehold_and", "prokaryotic_toehold_and", "eukaryotic_toehold_and",
      "antisense_not", "crispr", "new_toehold", "TOEHOLD", "toehold ", ""]) {
      unavailable(getGateRegions(family, loopSequence, loopArchitecture));
    }
  });

  test("missing or malformed metadata returns a readable notice and no regions", () => {
    for (const architecture of [null, undefined, [], "{}", 42, false, {}]) {
      unavailable(getGateRegions("toehold", loopSequence, architecture));
    }
    for (const field of Object.keys(loopArchitecture)) {
      const architecture = { ...loopArchitecture };
      delete architecture[field];
      unavailable(loop(architecture));
    }
    const architecture = { ...trailingArchitecture };
    delete architecture.kozak_linker_len;
    unavailable(trailing(architecture));
  });

  test("malformed persisted sequences never throw before the structure response arrives", () => {
    for (const sequence of [null, undefined, 42, true, {}, [], "", loopSequence.toLowerCase(),
      loopSequence.slice(0, -1) + "N", loopSequence.slice(0, -1) + "T",
      " " + loopSequence, loopSequence + "\n"]) {
      unavailable(getGateRegions("prokaryotic_toehold", sequence, loopArchitecture));
    }
  });

  test("numeric metadata rejects coercion, nonfinite, fractional and out-of-bounds values", () => {
    const numericFields = Object.keys(loopArchitecture)
      .filter((key) => typeof loopArchitecture[key] === "number");
    for (const key of numericFields) {
      for (const value of [null, "3", true, NaN, Infinity, -Infinity, -1, 1.5,
        Number.MAX_SAFE_INTEGER + 1, loopSequence.length + 1]) {
        unavailable(loop({ ...loopArchitecture, [key]: value }));
      }
    }
    for (const key of ["toehold_length", "stem_pre_bulge_len", "stem_post_bulge_len", "loop_len"]) {
      unavailable(loop({ ...loopArchitecture, [key]: 0 }));
    }
    for (const value of [null, "3", NaN, Infinity, -1, 1.5, 200]) {
      unavailable(trailing({ ...trailingArchitecture, kozak_linker_len: value }));
    }
  });

  test("unsupported or contradictory initiation layouts never guess", () => {
    unavailable(loop({ ...loopArchitecture, kozak_layout: "unknown" }));
    unavailable(loop({ ...loopArchitecture, track: "unknown" }));
    unavailable(loop({ ...loopArchitecture, kozak_linker_len: 3 }));
    unavailable(trailing({ ...trailingArchitecture, track: "prokaryotic" }));
    unavailable(loop({ ...loopArchitecture, track: "eukaryotic" }));
  });

  test("AUG and named initiation motifs must match at their declared coordinates", () => {
    unavailable(loop(loopArchitecture, loopSequence.slice(0, 50) + "ACG" + loopSequence.slice(53)));
    unavailable(loop(loopArchitecture, loopSequence.slice(0, 33) + "C" + loopSequence.slice(34)));
    unavailable(trailing(trailingArchitecture,
      trailingSequence.slice(0, 69) + "A" + trailingSequence.slice(70)));
    unavailable(trailing(trailingArchitecture,
      trailingSequence.slice(0, 75) + "ACG" + trailingSequence.slice(78)));
  });

  test("boundaries never clip, normalize or shift onto a nearby motif", () => {
    unavailable(loop({ ...loopArchitecture, aug_index: 51 }));
    unavailable(loop({ ...loopArchitecture, leader_len: 0 }));
    unavailable(loop({ ...loopArchitecture, linker_len: 19 }));
    unavailable(loop(loopArchitecture, loopSequence.slice(0, -1)));
    unavailable(loop(loopArchitecture, loopSequence + "A"));
    unavailable(loop(loopArchitecture, " " + loopSequence));
    unavailable(loop(loopArchitecture, loopSequence.toLowerCase()));
    // An extra AUG in the toehold cannot repair an incorrect stored AUG.
    const decoy = loopSequence.slice(0, 3) + "AUG" + loopSequence.slice(6, 50) +
      "ACG" + loopSequence.slice(53);
    unavailable(loop(loopArchitecture, decoy));
  });

  test("regions are in bounds, nonoverlapping and use one color per legend label", () => {
    for (const [result, sequence] of [[loop(), loopSequence], [trailing(), trailingSequence]]) {
      const legend = new Map();
      let previousEnd = 0;
      for (const { label, start, end, color } of result.regions) {
        assert(Number.isSafeInteger(start) && Number.isSafeInteger(end));
        assert(start >= previousEnd && end > start && end <= sequence.length);
        assert.match(color, /^#[\da-f]{6}$/i);
        if (legend.has(label)) assert.equal(color, legend.get(label));
        else legend.set(label, color);
        previousEnd = end;
      }
      assert.equal(new Set(legend.values()).size, legend.size);
    }
  });

  test("inputs remain unchanged after mapping", () => {
    const frozen = Object.freeze({ ...loopArchitecture });
    assert.deepEqual(loop(frozen), loop());
    assert.deepEqual(frozen, loopArchitecture);
  });

  test("provenance never promotes stored structures to predicted OFF or ON folds", () => {
    assert.equal(getStructureProvenanceLabel("intended_target"), "Intended target structure");
    for (const kind of [null, undefined, "", "mfe", "predicted_off", "predicted_on", {}, 1]) {
      assert.equal(getStructureProvenanceLabel(kind), "Stored structure · provenance unspecified");
    }
  });

  test("multicomponent candidates explicitly show only the primary stored switch", () => {
    for (const value of [null, undefined, {}, "two", [], [{ design_id: "one" }]]) {
      assert.equal(getPrimarySwitchNotice(value), null);
    }
    const notice = getPrimarySwitchNotice([
      { design_id: "one", switch_sequence: "ACGU" },
      { design_id: "two", switch_sequence: "GCAU" },
    ]);
    assert.match(notice, /primary switch only/);
    assert.match(notice, /other component switches are not stored/);
  });

  console.log(`RNA structure adapter: ${checks} contracts passed.`);
} finally {
  rmSync(bundle, { force: true });
}
