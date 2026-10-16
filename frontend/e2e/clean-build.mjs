/** Run with npm run test:clean-build in a fresh checkout after npm ci. */
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { writeFile, unlink } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const frontend = resolve(import.meta.dirname, "..");
const routeTree = resolve(frontend, "src/routeTree.gen.ts");
assert(!existsSync(routeTree), "Run this regression in a fresh checkout without a generated route tree");
assert(process.env.npm_execpath, "Run via npm run test:clean-build");
const build = () => spawnSync(process.execPath, [process.env.npm_execpath, "run", "build"], {
  cwd: frontend, encoding: "utf8",
});
const clean = build();
assert.equal(clean.status, 0, clean.error?.message || clean.stdout + clean.stderr);
assert(existsSync(routeTree), "The standard build generates the route tree");
assert(existsSync(resolve(frontend, "../src/static/app/index.html")), "The standard build emits the SPA");

// Vite transpilation alone accepts this: the standard build must still reject it.
const invalidSource = resolve(frontend, "src/clean-build-type-error.ts");
await writeFile(invalidSource, 'export const cleanBuildTypeError: string = 123;\n', { flag: "wx" });
try {
  const invalid = build();
  assert.notEqual(invalid.status, 0, "The standard build must reject a TypeScript error");
  assert.match(invalid.stdout + invalid.stderr, /clean-build-type-error\.ts.*error TS2322/);
} finally {
  await unlink(invalidSource);
}
console.log("Clean build passed without a generated route tree; TypeScript error was rejected.");
