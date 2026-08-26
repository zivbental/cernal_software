/**
 * Server-render LogicCircuitView across every circuit shape the engine can emit.
 *
 * This exists because the component originally hardcoded genes[0..3] — it was drawn
 * against a fixed four-gene mockup, so any real circuit with fewer genes crashed the
 * results page. TypeScript could not catch that; only rendering it can.
 */
import { build } from "esbuild";
import { readFileSync, rmSync } from "node:fs";
import path from "node:path";

const entry = "e2e/.render-entry.tsx";
const bundle = "e2e/.render-bundle.mjs";

const CASES = {
  "1 activator, no repressor": { activators: 1, repressors: 0 },
  "2 activators, no repressor": { activators: 2, repressors: 0 },
  "3 activators, no repressor": { activators: 3, repressors: 0 },
  "1 activator, 1 repressor": { activators: 1, repressors: 1 },
  "2 activators, 1 repressor": { activators: 2, repressors: 1 },
  "3 activators, 2 repressors": { activators: 3, repressors: 2 },
  "no genes at all": { activators: 0, repressors: 0 },
};

const src = `
import { renderToString } from "react-dom/server";
import { LogicCircuitView } from "@/components/results/LogicCircuit";

const LETTERS = "ABCDEF";

function makeLogic(activators, repressors) {
  const genes = [];
  for (let i = 0; i < activators; i++)
    genes.push({ name: LETTERS[i], role: "gene" + i, state: "ON", dir: "up" });
  for (let i = 0; i < repressors; i++)
    genes.push({ name: LETTERS[activators + i], role: "rep" + i, state: "OFF", dir: "down" });
  return {
    genes,
    midGate: "AND",
    outerGate: "AND",
    invert: repressors > 0,
    output: "Apoptosis inducer",
    caption: "IF ... -> EXPRESS X",
  };
}

globalThis.__render = (a, r) => renderToString(
  LogicCircuitView({ logic: makeLogic(a, r), activeGate: "mid", onGateClick: () => {} })
);
`;

import { writeFileSync } from "node:fs";
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

let failures = 0;
for (const [label, { activators, repressors }] of Object.entries(CASES)) {
  process.stdout.write(`  ${label.padEnd(30)}`);
  try {
    const html = globalThis.__render(activators, repressors);
    if (!html.includes("<svg") && activators + repressors > 0) {
      throw new Error("rendered no svg");
    }
    console.log(`ok  (${html.length} chars)`);
  } catch (e) {
    failures++;
    console.log(`FAILED — ${e.message.split("\n")[0]}`);
  }
}

rmSync(entry, { force: true });
rmSync(bundle, { force: true });
readFileSync;
process.exit(failures ? 1 : 0);
