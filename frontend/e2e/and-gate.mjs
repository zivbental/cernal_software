/**
 * Server-render the AND gate's evidence panel across the states a real run can be in.
 *
 * The panel is the one place a researcher sees why an AND candidate has the ON and OFF it has, so
 * it must never hide a failed sampler check, never turn an unmeasured value into a number, and
 * never imply a tie that was not determined. TypeScript cannot check any of that; rendering can.
 */
import { build } from "esbuild";
import { rmSync, writeFileSync } from "node:fs";
import path from "node:path";

const entry = "e2e/.and-entry.tsx";
const bundle = "e2e/.and-bundle.mjs";

const src = `
import { renderToString } from "react-dom/server";
import { AndGateEvidence } from "@/components/results/AndGateEvidence";

globalThis.__render = (info) => renderToString(AndGateEvidence({ info }));
`;
writeFileSync(entry, src);
await build({
  entryPoints: [entry],
  bundle: true,
  outfile: bundle,
  format: "esm",
  platform: "node",
  jsx: "automatic",
  alias: { "@": path.resolve("src") },
  external: ["react", "react-dom", "react/jsx-runtime", "react-dom/server"],
  logLevel: "error",
});
await import("./" + path.basename(bundle));

const state = (open_pct, verified) => ({ open_pct, draws: 2000, verified });
const GOOD = {
  on_pct: 99.5,
  off_pct: 0.5,
  off_source: "+A",
  on_minus_off_pp: 99.0,
  delta_g_kcal_per_mol: -17.6,
  tied_group: true,
  states: {
    alone: state(0.1, true),
    "+A": state(0.5, true),
    "+B": state(0.3, true),
    "+A+B": state(99.5, true),
  },
  controls: { mode: "exact_matrix_upper_bound", requested: 5, found: 5, max_open_pct: 0.09 },
  noise: { seed_to_seed_change_pp: 0.14 },
};

const CASES = {
  "a clean run shows ON, OFF and the tie": {
    info: GOOD,
    has: ["99.50%", "0.50%", ">+A<", "99.00 points", "-17.6 kcal/mol", "yes, indistinguishable", "passed"],
    lacks: ["FAILED", "unmeasured", 'role="alert"'],
  },
  "a failed sampler check is shown, not hidden": {
    info: { ...GOOD, states: { ...GOOD.states, "+A": state(0.5, false) } },
    has: ["FAILED", "The sampler check failed for", "+A", 'role="alert"', "kept but may be unreliable"],
    lacks: [],
  },
  "an unmeasured value reads unmeasured and never 0": {
    info: { ...GOOD, on_pct: null, off_pct: null, on_minus_off_pp: null, states: { ...GOOD.states, "+A+B": state(null, false) } },
    has: ["unmeasured", "FAILED"],
    lacks: ["0.00%", "0.00 points"],
  },
  "an undetermined tie is not claimed": {
    info: { ...GOOD, tied_group: null, noise: undefined },
    has: ["not determined", "seed-noise check was not run"],
    lacks: ["yes, indistinguishable"],
  },
  "missing blocks degrade to unavailable": {
    info: { on_pct: 80, off_pct: 2, off_source: null, on_minus_off_pp: 78 },
    has: ["80.00%", "unavailable"],
    lacks: ["NaN", "undefined"],
  },
};

let failures = 0;
for (const [label, { info, has, lacks }] of Object.entries(CASES)) {
  process.stdout.write(`  ${label.padEnd(54)}`);
  try {
    const html = globalThis.__render(info);
    for (const needle of has) if (!html.includes(needle)) throw new Error("missing: " + needle);
    for (const needle of lacks) if (html.includes(needle)) throw new Error("unexpected: " + needle);
    console.log("ok");
  } catch (e) {
    failures++;
    console.log(`FAILED — ${e.message.split("\n")[0]}`);
  }
}

rmSync(entry, { force: true });
rmSync(bundle, { force: true });
process.exit(failures ? 1 : 0);
