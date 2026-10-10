/**
 * RNA viewer browser regressions against the built SPA, using synthetic records only.
 * Run after npm run build: node e2e/rna-viewer-browser.mjs
 * Optional: PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium
 * Screenshots default to /tmp/cernal-rnaviz-qa (RNA_VIEWER_SCREENSHOT_DIR overrides).
 * RNA_VIEWER_FIXTURE_ONLY=1 starts just the HTTP fixtures for supported browser QA;
 * RNA_VIEWER_PORT and RNA_VIEWER_HOST optionally select its listening address.
 *
 * fixtures/rna-structure.json contains real engine.client.layout_stored_structure
 * output, generated from the repository root with PYTHONPATH=src python. Its annotated
 * sequence/architecture match e2e/rna-structure.mjs, and its stored structure is:
 * '.'*15 + '('*9 + '.'*3 + '('*6 + '.'*11 + ')'*6 + '.'*3 + ')'*9 + '.'*21.
 * To regenerate, call layout_stored_structure(sequence, structure,
 * structure_kind="intended_target") for the annotated example above and for
 * ("GCGAAACGC", "(((...)))"), ("ACGUUGCA", "........"), and ("G", ".").
 * Serialize those responses under hairpin, alternate, allDots, and single;
 * preserve the architecture object from e2e/rna-structure.mjs.
 * No scientific folding, authenticated browser profile, or user records are used.
 */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { extname, resolve } from "node:path";
import { chromium } from "playwright";

const root = resolve(import.meta.dirname, "../../src/static/app");
const fixture = JSON.parse(await readFile(new URL("./fixtures/rna-structure.json", import.meta.url), "utf8"));
const clone = (value) => structuredClone(value);
const shots = process.env.RNA_VIEWER_SCREENSHOT_DIR || "/tmp/cernal-rnaviz-qa";
const runA = "rna-run-a";
const runB = "rna-run-b";
const unknownRequests = [];
const requests = [];
const attempts = new Map();
const runs = [runA, runB].map((id, index) => ({
  id, status: "COMPLETED", organism: index ? "Synthetic second run" : "Synthetic RNA viewer QA",
  created_at: "2026-10-09T12:00:00Z", stage: "Completed", engine_version: "fixture",
  seed: 42, params_snapshot: { payload: { outputs: ["gfp", "other"] } },
  warnings: [], counts: { candidates: index ? 2 : 57, artifacts: 0 },
}));
const version = {
  app_version: "rna-browser-fixture", engine: "LocalEngine", engine_version: "fixture",
  reviewer_login_enabled: false, gate_families: [], supported_hosts: [],
  supported_outputs: [], input_modes: [], limits: {}, constraints: {}, scoring_profiles: [],
};
const cases = new Map();

function makeCandidate(rank, { runId = runA, name = `hairpin-${rank}`, layout = fixture.hairpin,
  design = {}, ...other } = {}) {
  const id = `${runId}-candidate-${rank}`;
  const candidate = {
    id, run_id: runId, rank, engine_ref: `rna-${name}`, overall_score: 0.99 - rank * 0.005,
    gate_family: "prokaryotic_toehold", logic_type: "SINGLE", summary: `Synthetic ${name}`,
    warnings: [], is_rejected: false, rejection_reason: "", output: rank === 2 ? "Custom" : "GFP",
    triggers: { features: [{ gene_id: "SYNTHETIC_INPUT", gene_symbol: "Fixture input" }] },
    design: {
      switch_sequence: layout?.sequence ?? fixture.hairpin.sequence,
      structure: layout?.structure ?? fixture.hairpin.structure,
      structure_kind: "intended_target", architecture: clone(fixture.architecture),
      plasmid_segments: [], logic_graph: { genes: [], output: "GFP" }, ...design,
    }, metrics: [], ...other,
  };
  cases.set(id, { candidate, layout: clone(layout) });
  return candidate;
}

const main = Array.from({ length: 57 }, (_, index) => makeCandidate(index + 1));
function replace(rank, options) { main[rank - 1] = makeCandidate(rank, options); }
replace(1, { name: "annotated-hairpin" });
replace(2, { name: "distinct-hairpin", layout: fixture.alternate, design: { architecture: null } });
replace(3, { name: "all-dots", layout: fixture.allDots, design: { architecture: null } });
replace(4, { name: "single-base", layout: fixture.single, design: { architecture: null } });
replace(5, { name: "unknown-provenance", design: { structure_kind: "legacy_unknown" },
  layout: { ...fixture.hairpin, structure_kind: "legacy_unknown" } });
replace(6, { name: "bad-architecture", design: { architecture: { ...fixture.architecture, aug_index: 51 } } });
replace(7, { name: "multi-gate", logic_type: "AND", design: { component_switches: [{ design_id: "first" }, { design_id: "second" }] } });
const unavailable = {
  ...fixture.hairpin, status: "unavailable", sequence: "", structure: "", bases: [], links: [],
  reason: "This candidate has no stored sequence and structure to display.",
};
const missingCases = [
  [8, "missing-both", undefined, undefined], [9, "empty-sequence", "", fixture.hairpin.structure],
  [10, "null-sequence", null, fixture.hairpin.structure], [11, "missing-structure", fixture.hairpin.sequence, undefined],
  [12, "empty-structure", fixture.hairpin.sequence, ""], [13, "null-structure", fixture.hairpin.sequence, null],
  [23, "missing-sequence", undefined, fixture.hairpin.structure],
];
for (const [rank, name, sequence, structure] of missingCases) {
  replace(rank, { name, layout: unavailable, design: { switch_sequence: sequence, structure } });
}
replace(14, { name: "invalid-saved", design: { structure: "(".repeat(83) },
  layout: { ...unavailable, status: "invalid", reason: "Stored dot-bracket structure is unbalanced." } });
replace(15, { name: "http-retry" });
replace(16, { name: "layout-retry" });
replace(17, { name: "mismatched-sequence", layout: { ...fixture.hairpin,
  sequence: "A" + fixture.hairpin.sequence.slice(1) }, design: { switch_sequence: fixture.hairpin.sequence } });
replace(18, { name: "invalid-coordinates", layout: { ...fixture.hairpin,
  bases: fixture.hairpin.bases.map((base, index) => index ? base : { ...base, x: null }) } });
replace(19, { name: "invalid-pairs", layout: { ...fixture.hairpin,
  links: [{ source: 0, target: 1000 }, ...fixture.hairpin.links.slice(1)] } });
replace(20, { name: "missing-bases", layout: { ...fixture.hairpin, bases: undefined } });
replace(21, { name: "null-response", layout: null });
replace(22, { name: "duplicate-pairs", layout: { ...fixture.hairpin,
  links: [fixture.hairpin.links[1], ...fixture.hairpin.links.slice(1)] } });
replace(24, { name: "short-bases", layout: { ...fixture.hairpin, bases: fixture.hairpin.bases.slice(1) } });
replace(25, { name: "malformed-pair", layout: { ...fixture.hairpin, links: [null, ...fixture.hairpin.links.slice(1)] } });
replace(26, { name: "wrong-base-index", layout: { ...fixture.hairpin,
  bases: fixture.hairpin.bases.map((base, index) => index ? base : { ...base, index: 2 }) } });
replace(27, { name: "delayed-response", layout: fixture.alternate, design: { architecture: null } });
replace(28, { name: "malformed-trigger-features", triggers: { features: [null, 42, "x", {}] } });
replace(51, { name: "page-two-distinct", layout: fixture.alternate, design: { architecture: null } });
replace(57, { name: "last-single", layout: fixture.single, design: { architecture: null } });
const second = [
  makeCandidate(1, { runId: runB, name: "second-run-distinct", layout: fixture.alternate, design: { architecture: null } }),
  makeCandidate(2, { runId: runB, name: "second-run-full" }),
];

function respond(res, body, status = 200) {
  res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" });
  res.end(JSON.stringify(body));
}
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://127.0.0.1");
    const path = url.pathname;
    if (path.startsWith("/api/")) {
      requests.push({ path, query: Object.fromEntries(url.searchParams), method: req.method });
      if (req.method !== "GET") {
        unknownRequests.push(`${req.method} ${path}`);
        return respond(res, { error: { message: "Read-only fixtures" } }, 405);
      }
      if (path === "/api/auth/me") return respond(res, { id: 1, username: "isolated-rna-test", is_staff: false });
      if (path === "/api/version") return respond(res, version);
      if (path === "/api/runs") return respond(res, runs);
      for (const run of runs) {
        const prefix = `/api/runs/${run.id}`;
        if (path === prefix || path === `${prefix}/detail`) return respond(res, run);
        if (path === `${prefix}/artifacts`) return respond(res, []);
        if (path === `${prefix}/candidates`) {
          let items = [...(run.id === runA ? main : second)];
          if (url.searchParams.has("output")) items = items.filter(item => item.output === url.searchParams.get("output"));
          if (url.searchParams.has("min_score")) items = items.filter(item => item.overall_score >= Number(url.searchParams.get("min_score")));
          if (url.searchParams.get("sort") === "engine_ref") items.sort((a, b) => a.engine_ref.localeCompare(b.engine_ref));
          const offset = Number(url.searchParams.get("offset") || 0);
          return respond(res, { count: items.length, items: items.slice(offset, offset + Number(url.searchParams.get("limit") || 50)) });
        }
      }
      const match = path.match(/^\/api\/candidates\/([^/]+)(\/structure|\/annotations)?$/);
      if (match && cases.has(match[1])) {
        const { candidate, layout } = cases.get(match[1]);
        if (!match[2]) return respond(res, candidate);
        if (match[2] === "/annotations") return respond(res, []);
        const attempt = (attempts.get(candidate.id) || 0) + 1;
        attempts.set(candidate.id, attempt);
        if (candidate.run_id === runA && candidate.rank === 15 && attempt === 1) {
          return respond(res, { error: { code: "fixture_error", message: "Injected layout HTTP failure", detail: {} } }, 503);
        }
        if (candidate.run_id === runA && candidate.rank === 16 && attempt === 1) {
          return respond(res, { ...unavailable, status: "error", reason: "Stored structure layout could not be generated." });
        }
        if (candidate.run_id === runA && candidate.rank === 27) await new Promise(done => setTimeout(done, 1500));
        return respond(res, layout);
      }
      unknownRequests.push(`${req.method} ${path}`);
      return respond(res, { error: { message: "Unexpected fixture API request" } }, 404);
    }
    if (path === "/favicon.ico") { res.writeHead(204).end(); return; }
    let asset;
    if (path.startsWith("/static/app/assets/")) {
      asset = resolve(root, path.replace(/^\/static\/app\//, ""));
      if (!asset.startsWith(`${root}/assets/`)) { res.writeHead(404).end(); return; }
    } else if (path === "/" || path === "/dashboard" || /^\/runs\/[^/]+$/.test(path)) {
      asset = resolve(root, "index.html");
    } else {
      unknownRequests.push(`${req.method} ${path}`);
      res.writeHead(404).end(); return;
    }
    let body = await readFile(asset);
    // Remove optional remote font links/preconnects, keeping the app fully offline.
    if (asset.endsWith("index.html")) body = body.toString().replace(/<link\b[^>]*href="https:\/\/fonts\.(?:googleapis|gstatic)\.com[^>]*>/g, "");
    res.setHeader("Content-Type", ({ ".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml" })[extname(asset)] || "text/html");
    res.end(body);
  } catch (error) {
    unknownRequests.push(`${req.method} ${req.url}: ${error.message}`);
    res.writeHead(500).end();
  }
});
await new Promise(done => server.listen(Number(process.env.RNA_VIEWER_PORT || 0), process.env.RNA_VIEWER_HOST || "127.0.0.1", done));
const origin = `http://127.0.0.1:${server.address().port}`;

if (process.env.RNA_VIEWER_FIXTURE_ONLY === "1") {
  console.log(`RNA viewer fixtures: ${origin}/dashboard`);
  console.log(`Annotated run: ${origin}/runs/${runA}`);
  console.log("Synthetic data only. Candidates include missing data, malformed responses, retries, and delayed navigation.");
  for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.close(() => process.exit(0)));
} else {
  let browser;
  let page;
  let currentCheck = "launch";
  const failures = [];
  const pageErrors = [];
  const outbound = [];
  let passed = 0;
  await mkdir(shots, { recursive: true });
  try {
    browser = await chromium.launch({
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}),
    });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, serviceWorkers: "block" });
    await context.route("**/*", route => {
      if (new URL(route.request().url()).origin === origin) return route.continue();
      outbound.push(route.request().url());
      return route.abort("blockedbyclient");
    });
    page = await context.newPage();
    page.setDefaultTimeout(6000);
    page.on("pageerror", error => pageErrors.push(`${currentCheck}: ${error.message}`));

    async function check(label, action) {
      currentCheck = label;
      const errorCount = pageErrors.length;
      try {
        await action();
        assert.equal(pageErrors.length, errorCount, "No uncaught browser errors");
        passed++;
        console.log(`  ${label}: ok`);
      } catch (error) {
        failures.push(`${label}: ${error.message}`);
        const slug = label.replace(/\W+/g, "-");
        await page.screenshot({ path: `${shots}/FAIL-${slug}.png` }).catch(() => {});
        await writeFile(`${shots}/FAIL-${slug}.txt`, await page.locator("body").innerText().catch(() => "Page unavailable"));
        console.error(`  ${label}: FAILED — ${error.message.split("\n")[0]}`);
      }
    }
    const viewer = () => page.getByRole("region", { name: "Candidate RNA structure" });
    const svg = () => page.locator(".rna-structure-svg");
    const canvas = () => page.getByTestId("rna-canvas");
    const readout = () => viewer().locator('[aria-live="polite"]');
    const row = (candidate) => page.getByRole("button").filter({ has: page.getByText(candidate.engine_ref, { exact: true }) });
    async function openRun(id = runA) {
      await page.goto(`${origin}/runs/${id}`);
      await page.getByRole("heading", { name: "Computational Design Results" }).waitFor();
      await page.getByRole("button", { name: "RNA Structure", exact: true }).waitFor();
    }
    async function choose(rank, list = main) {
      const candidate = list.find(item => item.rank === rank);
      await row(candidate).click();
      await page.getByText(`${candidate.engine_ref} · RNA Structure`, { exact: true }).waitFor();
    }
    async function openRna(rank = 1) {
      await openRun();
      await page.getByRole("button", { name: "RNA Structure", exact: true }).click();
      if (rank !== 1) await choose(rank);
    }
    async function expectDiagram(layout, ref) {
      await svg().waitFor();
      await page.waitForFunction(({ sequence, ref }) => {
        const diagram = document.querySelector(".rna-structure-svg");
        return diagram?.querySelector("title")?.textContent.startsWith(`${ref}:`)
          && [...diagram.querySelectorAll(".rna-base text")].map(node => node.textContent).join("") === sequence;
      }, { sequence: layout.sequence, ref });
      assert.equal(await svg().count(), 1);
      assert.equal(await svg().locator(".rna-base").count(), layout.bases.length);
      assert.equal(await svg().locator("line[stroke-dasharray]").count(), layout.links.length);
      assert.deepEqual(await svg().locator(".rna-base circle").evaluateAll(nodes => nodes.map(node => ({
        x: Number(node.getAttribute("cx")), y: Number(node.getAttribute("cy")),
      }))), layout.bases.map(({ x, y }) => ({ x, y })));
      assert.deepEqual(await svg().locator("line[stroke-dasharray]").evaluateAll(nodes => nodes.map(node => (
        ["x1", "y1", "x2", "y2"].map(key => Number(node.getAttribute(key)))
      ))), layout.links.map(({ source, target }) => [layout.bases[source].x, layout.bases[source].y, layout.bases[target].x, layout.bases[target].y]));
      const box = (await svg().getAttribute("viewBox")).split(" ").map(Number);
      assert(box.every(Number.isFinite) && box[2] > 0 && box[3] > 0, "Finite positive diagram extent");
      await viewer().getByText(`${layout.sequence.length} nt · ${layout.links.length} base pairs`, { exact: true }).waitFor();
    }
    async function expectReset() {
      assert.equal(await svg().getAttribute("width"), "100%");
      assert.equal(await svg().getAttribute("height"), "380");
      assert.match(await svg().locator(":scope > g").getAttribute("transform"), /rotate\(0\)/);
      assert.equal(await svg().locator('[aria-pressed="true"]').count(), 0);
      assert.match(await readout().innerText(), /Select a nucleotide/);
    }

    async function openPrecisionFilters() {
      const toggle = page.getByRole("button", { name: "Precision Filters", exact: true });
      await toggle.waitFor();
      const slider = page.getByRole("slider", { name: "Minimum score", exact: true });
      // Results may unmount this panel while a new server-side filter loads.
      // Reopen it as a user would, whether the prior query was cached or not.
      if (!(await slider.isVisible())) await toggle.click();
      await slider.waitFor();
      return slider;
    }
    function candidateResponse(expected) {
      return page.waitForResponse(response => {
        const url = new URL(response.url());
        return url.pathname === `/api/runs/${runA}/candidates`
          && response.request().method() === "GET"
          && Object.entries(expected).every(([key, value]) => url.searchParams.get(key) === value);
      });
    }
    async function screenshotViewer(filename) {
      // Element screenshots scroll under the sticky app header. Hide only that
      // overlay for the crop; ordinary page screenshots retain the real header.
      await viewer().screenshot({ path: `${shots}/${filename}`,
        style: "header.sticky { visibility: hidden !important; }" });
    }

    await check("dashboard navigation and exact annotated geometry", async () => {
      await page.goto(`${origin}/dashboard`);
      await page.getByRole("heading", { name: "Dashboard", exact: true }).waitFor();
      await page.locator(`a[href="/runs/${runA}"]`).click();
      await page.getByRole("heading", { name: "Computational Design Results" }).waitFor();
      await page.getByRole("button", { name: "RNA Structure", exact: true }).waitFor();
      assert(!requests.some(request => request.path.endsWith("/structure")), "Structure is loaded lazily on its tab");
      const tabs = page.getByRole("button", { name: /^(Plasmid Map|Logic Circuit|RNA Structure)$/ });
      assert.deepEqual(await tabs.allTextContents(), ["Plasmid Map", "Logic Circuit", "RNA Structure"]);
      await page.getByRole("button", { name: "RNA Structure", exact: true }).click();
      await expectDiagram(fixture.hairpin, main[0].engine_ref);
      await viewer().getByRole("heading", { name: "Intended target structure", exact: true }).waitFor();
      assert.match(await viewer().innerText(), /not a predicted OFF\/ON fold or experimental evidence/);
      assert.equal(await viewer().getByRole("heading", { name: /predicted (OFF|ON)/ }).count(), 0);
      const regions = viewer().getByLabel("RNA regions");
      assert.deepEqual(await regions.getByRole("button").allTextContents(), [
        "Toehold 4–15", "Stem 16–24", "Stem 28–33", "Initiation loop 34–44",
        "Stem 45–50", "AUG 51–53", "Stem 54–62", "Linker 63–83",
      ]);
      await regions.getByRole("button", { name: "AUG 51–53", exact: true }).click();
      assert.match(await readout().innerText(), /A at position 51 · AUG · unpaired/);
      await svg().getByRole("button", { name: "G · position 16 · Stem", exact: true }).click();
      assert.equal(await readout().innerText(), "G at position 16 · Stem · paired with C at 62");
      await svg().getByRole("button", { name: "G · position 16 · Stem", exact: true }).press("ArrowRight");
      assert.match(await readout().innerText(), /C at position 17 · Stem · paired with G at 61/);
      assert.equal(await svg().locator('[data-base-index="16"]').evaluate(node => node === document.activeElement), true);
      await viewer().getByText("Stored dot-bracket structure", { exact: true }).click();
      assert.equal(await viewer().locator("pre").innerText(), fixture.hairpin.structure);
      await screenshotViewer("annotated-viewer.png");
    });

    await check("candidate switching clears geometry selection zoom and rotation", async () => {
      await openRna();
      await expectDiagram(fixture.hairpin, main[0].engine_ref);
      await viewer().getByRole("button", { name: "AUG 51–53", exact: true }).click();
      await page.getByRole("button", { name: "Zoom in RNA", exact: true }).click();
      await page.getByRole("button", { name: "Rotate RNA right", exact: true }).click();
      assert.equal(await svg().getAttribute("width"), "125%");
      assert.match(await svg().locator(":scope > g").getAttribute("transform"), /rotate\(90\)/);
      await choose(2);
      await expectDiagram(fixture.alternate, main[1].engine_ref);
      await expectReset();
      await choose(1);
      await expectDiagram(fixture.hairpin, main[0].engine_ref);
      await expectReset();
      await page.getByRole("button", { name: "Zoom out RNA", exact: true }).click();
      await page.getByRole("button", { name: "Rotate RNA left", exact: true }).click();
      await page.getByRole("button", { name: "Reset view", exact: true }).click();
      await expectReset();
    });

    await check("repeated tabs and interrupted late structure response", async () => {
      await openRna();
      await expectDiagram(fixture.hairpin, main[0].engine_ref);
      for (const name of ["Logic Circuit", "Plasmid Map", "Logic Circuit", "Plasmid Map"]) {
        await viewer().getByRole("button", { name: "AUG 51–53", exact: true }).click();
        await page.getByRole("button", { name: "Zoom in RNA", exact: true }).click();
        await page.getByRole("button", { name: "Rotate RNA right", exact: true }).click();
        await page.getByRole("button", { name, exact: true }).click();
        assert.equal(await svg().count(), 0);
        await page.getByRole("button", { name: "RNA Structure", exact: true }).click();
        await expectDiagram(fixture.hairpin, main[0].engine_ref);
        await expectReset();
      }
      await choose(27);
      await page.getByRole("status").filter({ hasText: "Loading saved RNA structure" }).waitFor();
      assert.equal(await svg().count(), 0, "No previous candidate diagram while the next response is pending");
      await choose(2);
      await expectDiagram(fixture.alternate, main[1].engine_ref);
      // Purposefully allow the stale delayed fixture to finish, then recheck identity.
      await page.waitForTimeout(1700);
      await expectDiagram(fixture.alternate, main[1].engine_ref);
      await expectReset();
    });

    await check("pagination output filters sort and empty recovery", async () => {
      await openRna();
      await expectDiagram(fixture.hairpin, main[0].engine_ref);
      const pages = page.getByRole("navigation", { name: "Candidate pages" });
      await pages.getByRole("button", { name: "Next", exact: true }).click();
      await pages.getByText("Page 2 of 2", { exact: true }).waitFor();
      await expectDiagram(fixture.alternate, main[50].engine_ref);
      await expectReset();
      await choose(57);
      await expectDiagram(fixture.single, main[56].engine_ref);
      await pages.getByRole("button", { name: "Previous", exact: true }).click();
      await expectDiagram(fixture.hairpin, main[0].engine_ref);
      await pages.getByRole("button", { name: "Last", exact: true }).click();
      await expectDiagram(fixture.alternate, main[50].engine_ref);
      await page.getByRole("button", { name: "Custom", exact: true }).click();
      await pages.getByText("Page 1 of 1", { exact: true }).waitFor();
      await expectDiagram(fixture.alternate, main[1].engine_ref);
      assert(requests.some(({ query }) => query.output === "Custom" && !query.offset));
      await (await openPrecisionFilters()).press("End");
      await page.getByText("No candidate is selected.", { exact: false }).waitFor();
      assert.equal(await svg().count(), 0);
      assert.equal(await canvas().count(), 0);
      const minimumScore = await openPrecisionFilters();
      assert.equal(await minimumScore.inputValue(), "100", "Score filter survives the empty-results remount");
      await minimumScore.press("Home");
      await expectDiagram(fixture.alternate, main[1].engine_ref);
      assert.equal(await (await openPrecisionFilters()).inputValue(), "0");
      await Promise.all([
        candidateResponse({ output: "Custom", sort: "engine_ref", include_rejected: null }),
        page.getByLabel("Sort by", { exact: true }).selectOption("engine_ref"),
      ]);
      await expectDiagram(fixture.alternate, main[1].engine_ref);
      await openPrecisionFilters();
      assert.equal(await page.getByLabel("Sort by", { exact: true }).inputValue(), "engine_ref");
      await Promise.all([
        candidateResponse({ output: "Custom", sort: "engine_ref", include_rejected: "true" }),
        page.getByLabel("Show rejected candidates", { exact: false }).check(),
      ]);
      await expectDiagram(fixture.alternate, main[1].engine_ref);
      await openPrecisionFilters();
      assert(await page.getByLabel("Show rejected candidates", { exact: false }).isChecked());
      await Promise.all([
        candidateResponse({ output: null, sort: "engine_ref", include_rejected: "true" }),
        page.getByRole("button", { name: "All outputs", exact: true }).click(),
      ]);
      await page.waitForFunction(() => document.body.textContent.includes("57 matching candidates"));
      // The uncached all-output query resets selection to its first sorted row.
      await expectDiagram(fixture.allDots, main[2].engine_ref);
      await expectReset();
      await openPrecisionFilters();
      assert.equal(await page.getByLabel("Sort by", { exact: true }).inputValue(), "engine_ref");
      assert(await page.getByLabel("Show rejected candidates", { exact: false }).isChecked());
      assert(requests.some(({ query }) => query.sort === "engine_ref" && query.include_rejected === "true"));
      assert(requests.some(({ query }) => query.offset === "50"));
      assert(requests.some(({ query }) => query.min_score === "1"));
    });

    await check("Back Forward and switching runs never reuse a stale canvas", async () => {
      await page.goto(`${origin}/dashboard`);
      await page.locator(`a[href="/runs/${runA}"]`).click();
      await page.getByRole("button", { name: "RNA Structure", exact: true }).click();
      await expectDiagram(fixture.hairpin, main[0].engine_ref);
      await page.getByRole("button", { name: "Rotate RNA right", exact: true }).click();
      await page.getByRole("link", { name: "Run", exact: true }).click();
      await page.getByRole("heading", { name: "Dashboard", exact: true }).waitFor();
      assert.equal(await svg().count(), 0);
      await page.locator(`a[href="/runs/${runB}"]`).click();
      await page.getByRole("button", { name: "Plasmid Map", exact: true }).waitFor();
      assert.equal(await svg().count(), 0);
      await page.getByRole("button", { name: "RNA Structure", exact: true }).click();
      await expectDiagram(fixture.alternate, second[0].engine_ref);
      await expectReset();
      await page.goBack();
      await page.getByRole("heading", { name: "Dashboard", exact: true }).waitFor();
      assert.equal(await svg().count(), 0);
      await page.goBack();
      await page.getByRole("button", { name: "RNA Structure", exact: true }).click();
      await expectDiagram(fixture.hairpin, main[0].engine_ref);
      await expectReset();
      await page.goForward();
      await page.getByRole("heading", { name: "Dashboard", exact: true }).waitFor();
      await page.goForward();
      await page.getByRole("button", { name: "RNA Structure", exact: true }).click();
      await expectDiagram(fixture.alternate, second[0].engine_ref);
      await expectReset();
    });

    await check("unknown provenance architecture fallback and primary-only notice", async () => {
      await openRna(5);
      await expectDiagram(fixture.hairpin, main[4].engine_ref);
      await viewer().getByRole("heading", { name: "Stored structure · provenance unspecified", exact: true }).waitFor();
      assert.match(await viewer().innerText(), /no predicted OFF\/ON state is inferred/);
      assert.equal(await viewer().getByRole("heading", { name: "Intended target structure", exact: true }).count(), 0);
      await choose(6);
      await expectDiagram(fixture.hairpin, main[5].engine_ref);
      assert.match(await viewer().innerText(), /Region annotations unavailable:/);
      assert.equal(await viewer().getByLabel("RNA regions").count(), 0);
      await choose(7);
      await expectDiagram(fixture.hairpin, main[6].engine_ref);
      assert.match(await viewer().innerText(), /primary switch only/);
      assert.match(await viewer().innerText(), /other component switches are not stored/);
    });

    await check("malformed trigger feature records cannot crash a valid drawing", async () => {
      await openRna(28);
      await expectDiagram(fixture.hairpin, main[27].engine_ref);
      assert.equal(await viewer().getByText(/^Inputs?:/).count(), 0);
      await viewer().getByRole("button", { name: "AUG 51–53", exact: true }).click();
      assert.match(await readout().innerText(), /A at position 51 · AUG/);
    });

    await check("all-dots and one-nucleotide are real drawable structures", async () => {
      await openRna(3);
      await expectDiagram(fixture.allDots, main[2].engine_ref);
      await svg().getByRole("button", { name: "A · position 1", exact: true }).click();
      assert.match(await readout().innerText(), /A at position 1 · unpaired in this structure/);
      await choose(4);
      await expectDiagram(fixture.single, main[3].engine_ref);
      await expectReset();
      assert.equal(await svg().getByText("5′", { exact: true }).count(), 1);
      assert.equal(await svg().getByText("3′", { exact: true }).count(), 1);
      await svg().getByRole("button", { name: "G · position 1", exact: true }).press("ArrowRight");
      assert.match(await readout().innerText(), /G at position 1 · unpaired/);
      await page.getByRole("button", { name: "Rotate RNA right", exact: true }).click();
      await expectDiagram(fixture.single, main[3].engine_ref);
    });

    for (const [rank, name] of missingCases) {
      await check(`${name} displays unavailable without an invented diagram`, async () => {
        await openRna(rank);
        await page.getByText("RNA structure unavailable", { exact: true }).waitFor();
        await page.getByText("A missing structure is not evidence that the RNA is unpaired.", { exact: true }).waitFor();
        assert.equal(await canvas().count(), 0);
        assert.equal(await svg().count(), 0);
        await choose(1);
        await expectDiagram(fixture.hairpin, main[0].engine_ref);
      });
    }
    await check("invalid persisted dot-bracket displays an honest failure", async () => {
      await openRna(14);
      await page.getByRole("alert").filter({ hasText: "Saved RNA structure is invalid" }).waitFor();
      assert.equal(await svg().count(), 0);
    });
    for (const rank of [17, 18, 19, 20, 22, 24, 25, 26]) {
      await check(`${main[rank - 1].engine_ref} rejects malformed layout geometry`, async () => {
        await openRna(rank);
        await page.getByRole("alert").filter({ hasText: "drawing data does not match" }).waitFor();
        assert.equal(await svg().count(), 0);
        await choose(1);
        await expectDiagram(fixture.hairpin, main[0].engine_ref);
      });
    }
    for (const rank of [15, 16]) {
      await check(`${rank === 15 ? "HTTP error" : "layout error status"} is retryable`, async () => {
        attempts.delete(main[rank - 1].id);
        await openRna(rank);
        await page.getByRole("alert").filter({ hasText: rank === 15 ? "Could not load the RNA structure" : "RNA drawing could not be generated" }).waitFor();
        assert.equal(await svg().count(), 0);
        assert.equal(attempts.get(main[rank - 1].id), 1, "No automatic retry loop");
        await page.getByRole("button", { name: "Retry structure", exact: true }).click();
        await expectDiagram(fixture.hairpin, main[rank - 1].engine_ref);
        assert.equal(attempts.get(main[rank - 1].id), 2);
      });
    }

    await check("mobile width contains the viewer and its zoom overflow", async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      await openRna();
      await expectDiagram(fixture.hairpin, main[0].engine_ref);
      await screenshotViewer("mobile-viewer.png");
      await viewer().scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${shots}/mobile-page.png` });
      const measure = () => page.evaluate(() => {
        const viewer = document.querySelector('[aria-label="Candidate RNA structure"]');
        const canvas = document.querySelector('[data-testid="rna-canvas"]');
        const rect = viewer.getBoundingClientRect();
        return { viewport: innerWidth, document: document.documentElement.scrollWidth,
          left: rect.left, right: rect.right, client: canvas.clientWidth, scroll: canvas.scrollWidth };
      });
      let sizes = await measure();
      assert(sizes.left >= 0 && sizes.right <= sizes.viewport + 1, `Viewer fits 390px: ${JSON.stringify(sizes)}`);
      assert(sizes.document <= sizes.viewport + 1, `No document-level horizontal overflow: ${JSON.stringify(sizes)}`);
      await page.getByRole("button", { name: "Zoom in RNA", exact: true }).click();
      await page.getByRole("button", { name: "Zoom in RNA", exact: true }).click();
      sizes = await measure();
      assert(sizes.scroll > sizes.client, "Zoom overflow remains inside the drawing canvas");
      assert(sizes.document <= sizes.viewport + 1, "Zoom does not widen the page");
      await page.getByRole("button", { name: "Reset view", exact: true }).click();
      await expectReset();
      await page.setViewportSize({ width: 1440, height: 1100 });
    });

    await check("null layout response is contained without crashing the results", async () => {
      await openRna(21);
      await page.getByRole("alert").filter({ hasText: /drawing data does not match|Could not load the RNA structure|No diagram is shown/ }).waitFor();
      assert.equal(await svg().count(), 0);
      await choose(1);
      await expectDiagram(fixture.hairpin, main[0].engine_ref);
    });

    assert.deepEqual(outbound, [], "No external browser requests");
    assert.deepEqual(unknownRequests, [], "No unhandled fixture requests or mutations");
    assert.equal(pageErrors.length, 0, `Uncaught page errors: ${pageErrors.join("; ")}`);
    assert.equal(failures.length, 0, failures.join("\n\n"));
    console.log(`RNA viewer browser: ${passed} checks passed, no page errors or unexpected requests. Screenshots: ${shots}`);
  } catch (error) {
    if (!failures.length && !pageErrors.length) failures.push(`${currentCheck}: ${error.message}`);
    throw error;
  } finally {
    await writeFile(`${shots}/report.json`, JSON.stringify({ passed, failures, pageErrors, outbound, unknownRequests, requests }, null, 2) + "\n");
    await browser?.close();
    await new Promise(done => server.close(done));
  }
}
