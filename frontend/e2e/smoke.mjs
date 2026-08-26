/**
 * Browser smoke test: does the SPA actually render and drive the API?
 *
 * A clean `vite build` proves nothing about runtime — this catches a crash on mount,
 * a bad hook, or a route that throws. Run against a live `./do dev` + `./do worker`.
 *
 *   node e2e/smoke.mjs [outputDir]
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const ORIGIN = process.env.ORIGIN ?? "http://127.0.0.1:8000";
const OUT = process.argv[2] ?? "e2e/shots";
const USER = process.env.CERNAL_USER ?? "rosalind";
const PASS = process.env.CERNAL_PASS ?? "franklin-1952";

mkdirSync(OUT, { recursive: true });

const errors = [];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => {
  if (m.type() === "error") errors.push(`console: ${m.text()}`);
});

const step = async (name, fn) => {
  process.stdout.write(`  ${name.padEnd(34)}`);
  try {
    await fn();
    await page.screenshot({ path: `${OUT}/${name.replace(/\W+/g, "-")}.png`, fullPage: true });
    console.log("ok");
  } catch (e) {
    console.log(`FAILED — ${e.message.split("\n")[0]}`);
    await page.screenshot({ path: `${OUT}/FAIL-${name.replace(/\W+/g, "-")}.png` });
    throw e;
  }
};

try {
  await step("login page renders", async () => {
    await page.goto(`${ORIGIN}/login`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "Sign in" }).waitFor({ timeout: 10000 });
  });

  await step("sign in", async () => {
    await page.getByLabel("Username").fill(USER);
    await page.getByLabel("Password").fill(PASS);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL("**/projects", { timeout: 15000 });
  });

  await step("projects list", async () => {
    await page.getByRole("heading", { name: "Projects" }).waitFor({ timeout: 10000 });
  });

  await step("project detail", async () => {
    const card = page.locator('a[href^="/projects/"]').first();
    await card.waitFor({ timeout: 10000 });
    await card.click();
    await page.getByRole("heading", { name: /New circuit|Datasets|Runs/ }).first().waitFor({ timeout: 10000 });
  });

  await step("compile wizard", async () => {
    await page.getByRole("link", { name: /New circuit/ }).click();
    await page.getByRole("heading", { name: "Biological Compiler" }).waitFor({ timeout: 15000 });
    await page.getByText("Define Transcriptomic Inputs").waitFor();
    await page.getByText("Intracellular Logic Gate Assembly").waitFor();
    await page.getByText("Choose Downstream Output").waitFor();
  });

  await step("mechanism cards from capabilities", async () => {
    await page.getByText("Toehold Riboswitch").waitFor();
    await page.getByText("CRISPR-Cas sgRNA Gate").waitFor();
    const crispr = page.getByRole("button", { name: /CRISPR-Cas sgRNA Gate/ });
    if (!(await crispr.isDisabled())) throw new Error("planned mechanism should be disabled");
  });

  await step("direct trigger mode", async () => {
    await page.getByRole("button", { name: /Direct Trigger mRNA/ }).click();
    await page.locator("textarea").first().fill("AUGGCUAGCAAGGGCGAGGAGCUGUUCACCGGGGUG");
    await page.getByText("36 nt").waitFor({ timeout: 5000 });
  });

  await step("run page: results", async () => {
    const runId = process.env.RUN_ID;
    if (!runId) throw new Error("RUN_ID not provided");
    await page.goto(`${ORIGIN}/runs/${runId}`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "Optimized Plasmid Output" }).waitFor({ timeout: 15000 });
    await page.getByText("Ranked Candidates").waitFor();
    await page.getByText("Score decomposition").waitFor();
  });

  await step("logic circuit view", async () => {
    await page.getByRole("button", { name: "Logic Circuit" }).click();
    await page.waitForTimeout(600);
  });

  await step("rejected candidates with reasons", async () => {
    await page.getByRole("button", { name: /Precision Filters/ }).click();
    await page.getByRole("checkbox").check();
    await page.waitForTimeout(1200);
    await page.getByText(/leakage above the acceptable|Insufficient separation/).first().waitFor({ timeout: 10000 });
  });

  await step("quick guide", async () => {
    await page.goto(`${ORIGIN}/guide`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "How to compile a circuit" }).waitFor({ timeout: 10000 });
  });

  await step("about", async () => {
    await page.goto(`${ORIGIN}/about`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "CERNAL" }).first().waitFor({ timeout: 10000 });
  });
} finally {
  await browser.close();
}

const ignorable = (e) => e.includes("favicon") || e.includes("Failed to load resource: the server responded with a status of 404");
const real = errors.filter((e) => !ignorable(e));
if (real.length) {
  console.log(`\n${real.length} console/page errors:`);
  real.slice(0, 10).forEach((e) => console.log(`  ${e}`));
  process.exit(1);
}
console.log("\nNo page errors. Screenshots in " + OUT);
