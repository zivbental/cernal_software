/** Built SPA only, synthetic API fixtures only; no screening service is called. */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { resolve, extname, sep } from "node:path";
import { chromium } from "playwright";
import { report, sequence } from "./fixtures/screening.mjs";

const root = resolve(import.meta.dirname, "../../src/static/app");
const shots = resolve(process.env.SCREENING_SCREENSHOT_DIR || "test-results/screening");
const run = { id: "screening-run", status: "COMPLETED", organism: "Synthetic QA", engine_version: "fixture",
  params_snapshot: {}, warnings: [], counts: { candidates: 2, artifacts: 1 } };
const candidate = { id: "screening-candidate", run_id: run.id, rank: 1, engine_ref: "synthetic-first",
  overall_score: 0.5, gate_family: "toehold", summary: "Synthetic screening fixture", warnings: [],
  is_rejected: false, output: "GFP", triggers: { features: [] }, metrics: [],
  design: { switch_sequence: sequence, structure: "....", plasmid_segments: [], logic_graph: { genes: [] } } };
const other = { ...candidate, id: "other-candidate", rank: 2, engine_ref: "synthetic-second" };
let evidence;
let pendingRequests = 0;
let transition = false;
const unexpected = [];
const json = (res, body) => { res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify(body)); };
const server = createServer(async (req, res) => {
  const path = new URL(req.url, "http://localhost").pathname;
  if (path.startsWith("/api/")) {
    if (path === "/api/auth/me") return json(res, { id: 1, username: "screening-fixture" });
    if (path === "/api/version") return json(res, { engine_version: "fixture", gate_families: [] });
    if (path === `/api/runs/${run.id}` || path === `/api/runs/${run.id}/detail`) return json(res, run);
    if (path === `/api/runs/${run.id}/candidates`) return json(res, { count: 2, items: [candidate, other] });
    if (path === `/api/runs/${run.id}/artifacts`) return json(res, [{ id: "fixture-artifact", run_id: run.id,
      category: "sequences", label: "Synthetic file", name: "fixture.fasta", size_bytes: 4, download_url: "/fixture-download" }]);
    if (path === `/api/candidates/${candidate.id}`) {
      if (transition && ++pendingRequests > 1) evidence = report();
      return json(res, { ...candidate, sequence_screening: evidence });
    }
    if (path === `/api/candidates/${other.id}`) return json(res, other);
    if (path.endsWith("/annotations")) return json(res, []);
    unexpected.push(path); res.writeHead(404).end(); return;
  }
  if (path === "/favicon.ico") { res.writeHead(204).end(); return; }
  const asset = path.startsWith("/static/app/assets/") ? resolve(root, path.slice("/static/app/".length)) : resolve(root, "index.html");
  if (asset !== resolve(root, "index.html") && !asset.startsWith(`${root}${sep}assets${sep}`)) { res.writeHead(404).end(); return; }
  try {
    let body = await readFile(asset);
    if (asset.endsWith("index.html")) body = body.toString().replace(/<link\b[^>]*href="https:\/\/fonts\.(?:googleapis|gstatic)\.com[^>]*>/g, "");
    res.setHeader("Content-Type", ({ ".js": "application/javascript", ".css": "text/css" })[extname(asset)] || "text/html");
    res.end(body);
  } catch { res.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
let checks = 0;
try {
  await mkdir(shots, { recursive: true });
  browser = await chromium.launch(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/*", route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
  const panel = page.getByRole("region", { name: "Sequence screening", exact: true });
  async function scenario(data, label) {
    evidence = data;
    await page.goto(`${origin}/runs/${run.id}`);
    try { await panel.getByRole("status").filter({ hasText: label }).waitFor({ timeout: 10000 }); }
    catch (error) { console.error({ label, errors, unexpected, body: await page.locator("body").innerText() }); throw error; }
    assert.equal(await panel.getByRole("status").innerText(), label);
    checks++;
  }
  await scenario(undefined, "Not screened");
  for (const [state, label] of [["pending", "Screening pending"], ["error", "Screening failed"],
    ["unavailable", "Screening unavailable"], ["flagged", "Flagged for review"], ["clear", "No concerns detected by this screening"]]) {
    await scenario(report(state), label);
  }
  const disclosure = panel.locator("summary");
  await disclosure.focus(); await page.keyboard.press("Enter");
  await panel.getByText(report().subject.sha256, { exact: true }).waitFor();
  assert.match(await panel.innerText(), /Synthetic test database/);
  assert.match(await page.locator("body").innerText(), /Screening evidence is not currently embedded/);
  await panel.screenshot({ path: resolve(shots, "clear-desktop.png") });
  await page.getByRole("button", { name: /synthetic-second/ }).click();
  await panel.getByRole("status").filter({ hasText: "Not screened" }).waitFor();
  assert.doesNotMatch(await panel.innerText(), /No concerns detected by this screening/);
  checks++;
  await scenario(report("clear", { subject: { ...report().subject, sha256: "0".repeat(64) } }), "Screening result is stale or mismatched");
  await scenario(report("clear", { valid_until: "2020-01-01T00:00:00Z" }), "Screening result is stale or mismatched");
  await scenario({}, "Screening unavailable");
  for (const field of ["screened_at", "valid_until"]) {
    await scenario(report("clear", { [field]: "2026-01-01T00:00:00+99:99" }), "Screening unavailable");
    assert.doesNotMatch(await panel.innerText(), /No concerns detected by this screening/);
  }
  await scenario(report("clear", { valid_until: new Date(Date.now() + 6000).toISOString() }), "No concerns detected by this screening");
  await panel.getByRole("status").filter({ hasText: "Screening result is stale or mismatched" }).waitFor({ timeout: 10000 });
  checks++;
  transition = true; pendingRequests = 0;
  await scenario(report("pending"), "Screening pending");
  await panel.getByRole("status").filter({ hasText: "No concerns detected by this screening" }).waitFor({ timeout: 12000 });
  transition = false; checks++;
  await page.setViewportSize({ width: 390, height: 844 });
  await scenario(report("flagged"), "Flagged for review");
  await panel.locator("summary").click();
  await panel.screenshot({ path: resolve(shots, "flagged-mobile.png") });
  assert(await panel.evaluate(el => el.scrollWidth <= el.clientWidth), "screening panel must not overflow");
  assert.deepEqual(errors, []); assert.deepEqual(unexpected, []);
  console.log(`${checks} screening browser checks passed; screenshots: ${shots}`);
} finally { await browser?.close(); await new Promise(done => server.close(done)); }
