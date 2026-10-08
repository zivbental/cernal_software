/** Render the real help routes and validate their content, links, and fragments offline. */
import { build } from "esbuild";
import { execFileSync } from "node:child_process";
import {
  existsSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";

const entry = "e2e/.help-entry.tsx";
const bundle = "e2e/.help-bundle.mjs";
const repositoryRoot = path.resolve("..");
const immutableBase = "417f8385725a99f2d7d4bc835eeedeb5903d399f";
const githubBlob =
  /^https:\/\/github\.com\/zivbental\/cernal_software\/blob\/([^/]+)\/(.+)$/;

function routeFiles(directory = "src/routes", prefix = "") {
  const routes = new Map();
  for (const entryName of readdirSync(directory, { withFileTypes: true })) {
    const relative = path.join(prefix, entryName.name);
    const absolute = path.join(directory, entryName.name);
    if (entryName.isDirectory()) {
      for (const [route, file] of routeFiles(absolute, relative))
        routes.set(route, file);
    } else if (entryName.name.endsWith(".tsx")) {
      const name = relative.replace(/\.tsx$/, "").replace(/\/index$/, "");
      routes.set(
        name === "index" ? "/" : `/${name.replaceAll(path.sep, "/")}`,
        absolute,
      );
    }
  }
  return routes;
}

function idsIn(html) {
  return [...html.matchAll(/\sid="([^"]+)"/g)].map((match) => match[1]);
}

function hrefsIn(html) {
  return [...html.matchAll(/\shref="([^"]*)"/g)].map((match) => match[1]);
}

function sourceHasFragment(file, fragment) {
  const source = readFileSync(file, "utf8");
  return new RegExp(
    `id=[{]?['\"]${fragment.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}['\"]`,
  ).test(source);
}

function validateGithubSource(href, failures) {
  const match = href.match(githubBlob);
  if (!match) return false;
  const [, revision, file] = match;
  if (revision !== immutableBase)
    failures.push(
      `GitHub source link is not pinned to ${immutableBase}: ${href}`,
    );
  // CI uses a shallow checkout: the pinned historical commit may not be present.
  // Always verify the tracked local target; additionally verify the historical tree
  // when available. Live HTTP validation is a separate, network-dependent check.
  let hasRevision = false;
  try {
    execFileSync("git", ["cat-file", "-e", `${revision}^{commit}`], {
      cwd: repositoryRoot,
      stdio: "ignore",
    });
    hasRevision = true;
  } catch { /* A shallow clone legitimately omits historical objects. */ }
  if (hasRevision) {
    try {
      execFileSync("git", ["cat-file", "-e", `${revision}:${file}`], {
        cwd: repositoryRoot,
        stdio: "ignore",
      });
    } catch {
      failures.push(`GitHub source path does not exist at ${revision}: ${file}`);
    }
  }
  if (!existsSync(path.join(repositoryRoot, file)))
    failures.push(`GitHub source path does not exist locally: ${file}`);
  try {
    execFileSync("git", ["ls-files", "--error-unmatch", file], {
      cwd: repositoryRoot,
      stdio: "ignore",
    });
  } catch {
    failures.push(`GitHub source path is not tracked locally: ${file}`);
  }
  return true;
}

function validatePages(pages, routes, { checkGithub = true } = {}) {
  const failures = [];
  let links = 0;
  const anchors = new Map();

  for (const [route, html] of Object.entries(pages)) {
    const ids = idsIn(html);
    const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
    for (const id of new Set(duplicates))
      failures.push(`${route}: duplicate id ${id}`);
    anchors.set(route, new Set(ids));
  }

  for (const [sourceRoute, html] of Object.entries(pages)) {
    for (const href of hrefsIn(html)) {
      links += 1;
      if (
        !href ||
        /^(javascript|data|vbscript):/i.test(href) ||
        /example\.(com|org)|your-cernal-host|TODO|PLACEHOLDER/i.test(href)
      ) {
        failures.push(
          `${sourceRoute}: unsafe or placeholder href ${JSON.stringify(href)}`,
        );
        continue;
      }
      try {
        const parsed = new URL(href, `https://cernal.invalid${sourceRoute}`);
        if (!["http:", "https:"].includes(parsed.protocol))
          throw new Error("unsupported URL scheme");
      } catch {
        failures.push(`${sourceRoute}: malformed or unsafe href ${href}`);
        continue;
      }
      if (checkGithub && validateGithubSource(href, failures)) continue;
      if (/^https?:\/\//.test(href)) continue;
      if (!href.startsWith("/") && !href.startsWith("#")) {
        failures.push(`${sourceRoute}: ambiguous relative href ${href}`);
        continue;
      }

      const [routePart, fragment] = href.split("#");
      const targetRoute = routePart || sourceRoute;
      if (targetRoute === "/api/version") continue;
      const targetFile = routes.get(targetRoute);
      if (!targetFile) {
        failures.push(`${sourceRoute}: dangling route ${href}`);
        continue;
      }
      if (fragment) {
        const renderedAnchors = anchors.get(targetRoute);
        const found = renderedAnchors
          ? renderedAnchors.has(fragment)
          : sourceHasFragment(targetFile, fragment);
        if (!found) failures.push(`${sourceRoute}: dangling fragment ${href}`);
      }
    }
  }
  return { failures, links };
}

function validateTouchedMarkdown() {
  const failures = [];
  // Explicit scope keeps checks active after staging and in a clean CI checkout.
  const changed = [
    "README.md",
    "docs/README.md",
    "docs/user-help.md",
    "docs/software-development-log.md",
  ];
  for (const file of changed) {
    const source = readFileSync(path.join(repositoryRoot, file), "utf8");
    for (const match of source.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
      const href = match[1].split(/\s+["']/)[0];
      if (/^(https?:|mailto:|#)/.test(href)) continue;
      const [localPath] = href.split("#");
      if (
        !existsSync(path.resolve(repositoryRoot, path.dirname(file), localPath))
      ) {
        failures.push(`${file}: nonexistent local Markdown link ${href}`);
      }
    }
  }
  return failures;
}

function runNegativeControls(routes) {
  const controls = [
    [
      "bad route",
      { "/guide": '<a href="/definitely-missing">bad</a>' },
      "dangling route",
    ],
    [
      "missing fragment",
      { "/guide": '<a href="#missing">bad</a>' },
      "dangling fragment",
    ],
    [
      "unrendered fragment",
      { "/guide": '<a href="/compile#definitely-missing">bad</a>' },
      "dangling fragment",
    ],
    [
      "unsafe scheme",
      { "/guide": '<a href="javascript:void(0)">bad</a>' },
      "unsafe",
    ],
    [
      "malformed URL",
      { "/guide": '<a href="https://">bad</a>' },
      "malformed",
    ],
    [
      "duplicate id",
      { "/guide": '<div id="same"></div><div id="same"></div>' },
      "duplicate id",
    ],
    [
      "nonexistent source",
      {
        "/guide": `<a href="https://github.com/zivbental/cernal_software/blob/${immutableBase}/does/not/exist.ts">bad</a>`,
      },
      "does not exist",
    ],
  ];
  const failures = [];
  for (const [name, pages, expected] of controls) {
    const result = validatePages(pages, routes);
    if (!result.failures.some((failure) => failure.includes(expected)))
      failures.push(`${name} negative control was not detected`);
  }
  return { failures, count: controls.length };
}

writeFileSync(
  entry,
  `
import { renderToStaticMarkup } from "react-dom/server";
import { GuideContent } from "@/routes/guide";
import { UseCasesContent } from "@/routes/use-cases";
import { FaqContent } from "@/routes/faq";
globalThis.__help = {
  "/guide": renderToStaticMarkup(<GuideContent />),
  "/use-cases": renderToStaticMarkup(<UseCasesContent />),
  "/faq": renderToStaticMarkup(<FaqContent />),
};
`,
);

try {
  await build({
    entryPoints: [entry],
    bundle: true,
    outfile: bundle,
    format: "esm",
    platform: "node",
    packages: "external",
    jsx: "automatic",
    alias: { "@": path.resolve("src") },
    loader: { ".svg": "dataurl", ".png": "dataurl" },
    logLevel: "error",
  });
  await import(`./${path.basename(bundle)}`);
  const pages = globalThis.__help;
  const required = {
    "/guide": [
      "How to compile a circuit",
      "LocalEngine",
      "manifest.json",
      "summary.csv",
      "separate output-specific candidates",
      "Show rejected candidates",
    ],
    "/use-cases": [
      "Choose a supported workflow",
      "small real run",
      "What CERNAL does not establish",
    ],
    "/faq": [
      "CERNAL_ENGINE=engine.client.LocalEngine",
      "manifest.json",
      "summary.csv",
      "owner-scoped",
    ],
  };
  const failures = [];
  for (const [route, phrases] of Object.entries(required)) {
    for (const phrase of phrases)
      if (!pages[route].includes(phrase))
        failures.push(`${route}: missing ${JSON.stringify(phrase)}`);
  }
  const prohibited = [
    /no manifest(?:\.json)?/i,
    /no automatic provenance bundle/i,
  ];
  for (const [route, html] of Object.entries(pages)) {
    for (const phrase of prohibited)
      if (phrase.test(html))
        failures.push(`${route}: prohibited false manifest claim ${phrase}`);
  }

  const routes = routeFiles();
  const validation = validatePages(pages, routes);
  failures.push(...validation.failures, ...validateTouchedMarkdown());
  const negative = runNegativeControls(routes);
  failures.push(...negative.failures);
  if (failures.length) throw new Error(failures.join("\n"));
  console.log(
    `help content ok (${Object.keys(pages).length} rendered pages; ${validation.links} links; ${negative.count} negative controls)`,
  );
} finally {
  rmSync(entry, { force: true });
  rmSync(bundle, { force: true });
}
