import assert from "node:assert/strict";
import { build } from "esbuild";
import { rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { report, sequence } from "./fixtures/screening.mjs";

const bundle = new URL("./.screening-bundle.mjs", import.meta.url);
let checks = 0;
try {
  await build({ entryPoints: ["src/lib/sequence-screening.ts"], bundle: true, outfile: fileURLToPath(bundle),
    platform: "node", format: "esm", logLevel: "error" });
  const { assessScreening } = await import(bundle.href);
  const subject = { runId: "screening-run", candidateId: "screening-candidate", sequence };
  const now = Date.parse("2026-10-12T12:00:00Z");
  async function check(name, data, expected, target = subject, time = now) {
    const view = await assessScreening(data, target, time);
    assert.equal(view.state, expected, name);
    if (expected === "stale" || (expected === "unavailable" && data?.status !== "unavailable")) assert.equal(view.evidence, undefined, name);
    if (expected !== "clear") assert.notEqual(view.label, "No concerns detected by this screening", name);
    checks++; console.log(`  ${name}: ok`);
  }
  await check("legacy absent", undefined, "not_screened");
  await check("legacy null", null, "not_screened");
  for (const state of ["not_screened", "unavailable", "pending", "error", "flagged", "clear"]) {
    await check(state, report(state), state);
  }
  await check("malformed", {}, "unavailable");
  await check("unknown version", report("clear", { schema_version: 2 }), "unavailable");
  await check("unknown status", report("safe"), "unavailable");
  await check("unknown finding", report("flagged", { findings: ["raw hazardous output"] }), "unavailable");
  await check("wrong run", report(), "stale", { ...subject, runId: "another-run" });
  await check("wrong candidate", report(), "stale", { ...subject, candidateId: "another-candidate" });
  await check("changed sequence", report(), "stale", { ...subject, sequence: "UGCA" });
  await check("wrong length", report("clear", { subject: { ...report().subject, length: 5 } }), "stale");
  await check("wrong scope", report("clear", { subject: { ...report().subject, scope: "full_construct" } }), "unavailable");
  await check("wrong normalization", report("clear", { subject: { ...report().subject, normalization: "dna" } }), "unavailable");
  await check("expired", report("clear", { valid_until: "2026-10-12T12:00:00Z" }), "stale");
  await check("future timestamp", report("clear", { screened_at: "2099-02-01T00:00:00Z" }), "stale");
  await check("inverted time", report("clear", { valid_until: "2025-01-01T00:00:00Z" }), "stale");
  for (const field of ["screened_at", "valid_until"]) {
    for (const offset of ["+99:99", "+24:00", "+00:60"]) {
      await check(`invalid ${field} offset ${offset}`, report("clear", {
        [field]: `2026-01-01T00:00:00${offset}`,
      }), "unavailable");
    }
  }
  for (const field of ["screened_at", "valid_until", "provenance"]) {
    await check(`missing ${field}`, report("clear", { [field]: null }), "unavailable");
  }
  await check("contradictory clear", report("clear", { findings: ["review_required"] }), "unavailable");
  await check("lowercase identity", report(), "clear", { ...subject, sequence: "acgu" });
  await check("invalid comparison time", report(), "unavailable", subject, Number.NaN);
  for (const invalid of ["ACGT", "AC GU", "", "ACGN"]) {
    await check("unverifiable alphabet", report(), "unavailable", { ...subject, sequence: invalid });
  }
  const crypto = globalThis.crypto;
  Object.defineProperty(globalThis, "crypto", { value: undefined, configurable: true });
  await check("missing digest API", report(), "unavailable");
  Object.defineProperty(globalThis, "crypto", { value: crypto, configurable: true });
  console.log(`${checks} screening checks passed`);
} finally { await rm(bundle, { force: true }); }
