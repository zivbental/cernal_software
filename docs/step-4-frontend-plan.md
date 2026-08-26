# Step 4 — Frontend integration plan

> **Planning document. Nothing here is implemented yet.**
> Read [`software-design.md`](software-design.md) first for the architecture this fits
> into, and [`api.md`](api.md) for the endpoints the frontend consumes.

This plan covers turning the Lovable design in `lovable_frontend_raw/` into a working
frontend on top of the Step 3 backend. Where the science is not ready, the mock engine
already supplies realistic data — so the UI can be finished and demonstrated end to end
before Step 5 lands.

---

## 1. What is actually in `lovable_frontend_raw/`

| Path | What it is | Use |
|---|---|---|
| `uploads/synth-logic-builder-main/` | **The React app.** TanStack Start + shadcn/ui + Tailwind v4 | **The thing we vendor** |
| ↳ `src/routes/index.tsx` | 2,096 lines: the entire design in one file | Source of every screen |
| ↳ `src/components/ui/*` (50 files) | Untouched shadcn/ui primitives | Keep as-is |
| ↳ `src/styles.css` | Design tokens (oklch, light + dark) | Keep as-is |
| ↳ `src/assets/` | Animated CERNAL logo (SVG), logo PNG | Keep |
| `CERNAL_Overview.md` | Product narrative, 3-step flow, design language | Requirements source |
| `CERNAL Compiler.dc.html` | Design-canvas render of the compiler screen | Visual reference |
| `Quick Guide.dc.html` | Design-canvas Quick Guide page | Content source for `/guide` |
| `About Us.dc.html` | Design-canvas About page | Content source for `/about` |
| `guide-shots/` (20 PNGs) | Annotated screenshots for the Quick Guide | Assets for `/guide` |
| `assets/`, `screenshots/`, `uploads/*.png` | Logos, team photos, cows, diagrams | Cherry-pick |
| `uploads/iGEM_Wiki_Test-main/` | Separate iGEM wiki site | **Out of scope** |
| `diagrams.jsx`, `support.js`, `image-slot.js` | Design-canvas runtime, not app code | **Discard** |
| `*:Zone.Identifier` | Windows download markers | **Discard** (already gitignored) |

### Verdict

The React app is a **high-fidelity static mockup**, not a working client. Concretely:

- It has **one route** (`/`) rendering `Step1`, `Step3`, `Step4` stacked on a single page.
- `Step2` (the Boolean logic builder) **is written but never rendered**.
- `StepRail` is hardcoded to `active={3}` — there is no wizard state.
- All data is the `CANDIDATES` array literal at line 941. **Zero network calls.**
- No auth, no routing, no loading states, no error states, no forms that submit.

That is normal for a Lovable export and it is *good news*: the visual language, component
inventory and information design are done, which is the expensive part. What remains is
wiring, decomposition and the screens the mockup never needed.

---

## 2. The five structural problems

### 2.1 It is a server-rendered app; we need a static SPA

`package.json` pulls `@tanstack/react-start`, `nitro`, `wrangler`,
`@cloudflare/vite-plugin` and `@lovable.dev/vite-tanstack-config`. `src/server.ts` and
`src/start.ts` are SSR entry points. `wrangler.jsonc` targets Cloudflare Workers.

This directly contradicts [ADR 0003](decisions/0003-same-origin-spa-session-auth.md): we
serve a **static build from Django, same origin**, which is what makes session cookies
work with no CORS and no tokens in browser storage.

**Decision: strip TanStack *Start*, keep TanStack *Router*.** Plain Vite +
`@vitejs/plugin-react` + `@tanstack/react-router` in SPA mode + `@tailwindcss/vite`.
Delete `server.ts`, `start.ts`, `wrangler.jsonc`, and the Cloudflare/nitro/Lovable
plugins. Roughly 6 dependencies removed, one `vite.config.ts` written by hand.

This is the single biggest decision in Step 4 and warrants **ADR 0005**.

### 2.2 One 2,096-line file

Must be decomposed before anything else, or every subsequent change is a merge conflict
waiting to happen. See [§5](#5-target-file-layout).

### 2.3 The design assumes compilation is synchronous

The mockup shows Inputs → Payload → *results already present*. There is a "Compile &
Optimize" button that does nothing, and **no waiting state anywhere**.

Our backend is asynchronous by design: `POST /runs` returns **202 QUEUED**, a worker picks
it up, and the client polls `GET /api/runs/{id}` through `RUNNING` to `COMPLETED`.

**This is the most important reshaping in Step 4.** Steps 1–2 become a *form* that
submits; Step 3 becomes a *result page keyed by run id*, with a progress state in front of
it. It also means the run URL is shareable and survives a refresh — which the mockup's
single-page design cannot do.

### 2.4 The mockup's data model is richer than the engine's output

The mockup shows `bp`, `dynRange`, `gc`, `offTarget`, `successRate`, plasmid ring
segments, and a logic graph with `midGate`/`outerGate`/`invert`/`caption`. Our
`default-v1` profile emits six different metrics, and `design.logic_graph` is
`{inputs, operator, output}`.

**Do not paper over this in React.** Anything scientific must come from the engine
([§3](software-design.md) — the frontend performs no scientific computation). The fix is
to extend `MockEngine` and the scoring profile. See [§7](#7-engine-changes).

### 2.5 The mockup hardcodes its metric list

Six metric tiles are written out by name. If the scientific team changes the scoring
profile in Step 5 — which they will — a hardcoded UI silently shows the wrong thing.

**Decision: render metrics from data.** `GET /api/candidates/{id}` already returns
`metrics: [{name, raw_value, normalized_value, weight, direction}]`. The UI should map
over that array, with a display-name/unit lookup table for prettification and a sensible
fallback for unknown metrics. This is what design map 12's "report the decomposition, not
a single opaque score" actually requires.

---

## 3. Decisions to settle before writing code

| # | Question | Recommendation |
|---|---|---|
| 1 | SSR or static SPA? | **Static SPA.** ADR 0005. See §2.1 |
| 2 | Router? | Keep `@tanstack/react-router` (already a dependency, file-based routes) |
| 3 | Server state? | `@tanstack/react-query` — already a dependency, and polling is exactly its strength |
| 4 | Where does the project come from? The mockup has no project step | Add a project selector/name field to Step 1. Everything else in the backend hangs off `Project`, and "My Circuits" already implies it |
| 5 | Direct-trigger mode (no dataset) | Real second input mode. Make `AnalysisRun.dataset` nullable, add `input_mode`, extend `JobRequest`. See §6.2 |
| 6 | `.xlsx` upload | Add `openpyxl`. Biologists export from Excel/DESeq2; refusing xlsx will be the single most common complaint. One dependency, well-justified |
| 7 | Precision filters — server or client? | **Client-side.** A run has a few hundred candidates; fetch once, filter in memory. No API change, instant feedback |
| 8 | "Order Plasmid with Our Trusted Partner" | Stub. Disabled button with "Coming soon", or a `mailto:`. No backend |
| 9 | Boolean clause builder ("+ Add clause") | v1: fixed shape — Set A (up) AND NOT Set B (down). Arbitrary nested clauses deferred |
| 10 | Static content pages | React routes with content in TSX. No CMS, no backend |

---

## 4. Target route map

The mockup has one page. The product needs these:

| Route | Screen | Source | Status |
|---|---|---|---|
| `/login` | Sign in | — | **Missing from design** |
| `/` | Redirect → `/projects` | — | New |
| `/projects` | "My Circuits" — project list, empty state | Referenced by nav button only | **Missing from design** |
| `/projects/:id` | Project detail: datasets + run history | — | **Missing from design** |
| `/compile` · `/projects/:id/compile` | Wizard: Step 1 Inputs → Step 2 Logic → Step 3 Payload | `Step1`, `Step2`, `Step3` | Design exists (Step2 unrendered) |
| `/runs/:id` | Progress **or** results, depending on status | `Step4` covers results only | Progress **missing from design** |
| `/guide` | Quick Guide | `Quick Guide.dc.html` + `guide-shots/` | Content exists |
| `/use-cases` | Use Cases | Nav item only — **no content anywhere** | **Missing entirely** |
| `/about` | About Us | `About Us.dc.html` + team photos | Content exists |

Note the mockup's `StepRail` labels three steps (Inputs / Payload / Fulfillment) while
four `Step*` components exist. Recommended rail: **Inputs → Logic → Payload → Compile**,
with Fulfillment living at `/runs/:id` rather than as a rail step, because it is a
different resource with its own URL.

---

## 5. Target file layout

```
frontend/
├── index.html
├── package.json                 pruned: no start/nitro/wrangler/cloudflare
├── vite.config.ts               hand-written; base "/static/app/", /api proxy in dev
├── tsconfig.json
├── public/
│   └── guide/                   guide-shots/*.png
└── src/
    ├── main.tsx                 SPA entry (replaces server.ts/start.ts)
    ├── router.tsx
    ├── styles.css               ← unchanged from Lovable
    ├── assets/                  ← unchanged
    ├── api/
    │   ├── client.ts            fetch wrapper: credentials, CSRF header, error envelope
    │   ├── types.ts             generated from /api/openapi.json
    │   └── queries.ts           react-query hooks: useProjects, useRun, useCandidates…
    ├── components/
    │   ├── ui/                  ← unchanged shadcn primitives
    │   ├── layout/              Nav, Footer, Panel, SectionHeading, StepRail
    │   ├── icons/               BacteriaIcon, YeastIcon, HumanIcon, RnaIcon…
    │   ├── compile/             OrganismPicker, UploadZone, TriggerInput,
    │   │                        LogicBuilder, MechanismPicker, PayloadPicker,
    │   │                        AdvancedOptions, SliderRow
    │   └── results/             CandidateList, CandidateCard, MetricGrid,
    │                            PlasmidRing, LogicCircuitView, RNAKey,
    │                            ToeholdSimulation, PrecisionFilters, ExportMenu
    └── routes/
        ├── __root.tsx           ← keep, minus SSR bits
        ├── login.tsx            index.tsx  projects.tsx  projects.$id.tsx
        ├── compile.tsx          runs.$id.tsx
        └── guide.tsx            use-cases.tsx  about.tsx
```

Every component in `components/` is **lifted verbatim** from `index.tsx` where possible.
The visual work is done; do not redesign it while decomposing.

### Django side

- `vite build` → `src/static/app/`, `base: "/static/app/"`
- `config/urls.py` gains an SPA catch-all after `/admin/`, `/api/`, `/static/`, `/media/`
- `./do build-frontend`; `./do dev` builds the frontend if `src/static/app/` is missing

### Dev workflow

Three terminals: `./do dev` (:8000), `./do worker`, `npm run dev` (:5173 with `/api`
proxied to :8000). Session cookies work through the proxy because the browser only ever
sees one origin. Production is a single origin for real.

---

## 6. Backend gap analysis

### 6.1 What already works, unchanged

Auth + CSRF · projects CRUD · dataset upload with checksum and validation report · run
submission with idempotency · **polling with `stage`/`progress_pct`** · cancellation ·
candidate list with sort/filter/pagination · candidate detail with full metric
decomposition · artifact download · CSV export · annotations · `GET /api/version`
advertising gate families and scoring profiles.

That is most of the wizard and all of the results explorer.

### 6.2 Backend changes required

| # | Need | Change | Size |
|---|---|---|---|
| 1 | Direct trigger mRNA (no dataset) | `AnalysisRun.dataset` → nullable; add `input_mode` (`DE`/`DIRECT`); add `trigger_sequence`. Migration. `JobRequest` gains `input_mode` + `trigger_sequence` | **M** |
| 2 | `.tsv` upload | `csv.Sniffer` in `validate_expression_file` | S |
| 3 | `.xlsx` upload | Add `openpyxl`; convert to rows before the existing validator | S |
| 4 | Fold-change column | Accept `fold_change`, `foldchange`, `FC`, `log2FoldChange` as aliases for `log2fc` | S |
| 5 | 100 MB uploads | `MAX_DATASET_MB=100`; check streaming actually holds at that size | S |
| 6 | Config schema | Validate `params_snapshot` against a versioned schema (§6.3) instead of accepting free JSON | **M** |
| 7 | Mechanism choice | `crispr` and `antisense` gate families — register stubs so `/api/version` advertises them; UI can then show them honestly as unavailable-until-Step-5 | S |
| 8 | Run list across projects | `GET /api/runs?limit=` for "My Circuits" recency | S |
| 9 | GenBank export | New artifact kind from the engine, or an export endpoint | **M** — defer to Step 5 |

### 6.3 Run configuration schema v1

`params_snapshot` is currently untyped JSON. Every wizard input lands here, so it needs a
shape — this is the contract between the wizard and the engine:

```jsonc
{
  "schema_version": "1",
  "organism": "ecoli",              // ecoli | yeast | human
  "input_mode": "de",               // de | direct
  "trigger_sequence": null,         // ACGU string when input_mode = direct
  "logic": {
    "set_a": ["IL6", "TNF"],        // required-ON transcripts
    "set_b": ["FOXP3"],             // required-OFF transcripts
    "expression": "A AND NOT B"     // rendered caption; v1 shape is fixed
  },
  "mechanism": "toehold",           // mirrors gate_families[0]
  "payload": {
    "reporters": ["gfp"],           // gfp | mcherry | luciferase
    "markers": ["ampr"],            // ampr | apoptosis
    "custom_sequence": null
  },
  "constraints": {
    "max_leakage": 0.08,
    "min_mfe": -32,
    "min_off_target_score": 85,
    "max_length_bp": 5000,
    "target_gc": 50
  }
}
```

`constraints` maps onto the scoring profile's hard filters. Two options: pass them through
and let the engine apply them per run (flexible, but a run's score is then not comparable
across runs), or treat the sliders as *post-hoc client-side filters* over returned
candidates. **Recommendation: client-side for v1** — it matches decision #7, keeps scoring
comparable, and gives instant feedback. Record the values in `params_snapshot` regardless,
for reproducibility.

---

## 7. Engine changes

The mockup displays things the engine does not yet produce. These are **scientific
outputs**, so they belong in `src/engine/`, not in React.

### 7.1 Extend `CandidateResult.design`

```jsonc
{
  "switch_sequence": "...",         // exists
  "structure": "((((....))))",      // exists
  "toehold_length": 15,             // exists
  "sequence_length_bp": 4247,       // NEW — "bp" tile
  "plasmid_segments": [             // NEW — drives PlasmidRing
    {"kind": "promoter",   "name": "J23119", "length_bp": 35},
    {"kind": "switch",     "name": "toehold_A", "length_bp": 120},
    {"kind": "payload",    "name": "GFP", "length_bp": 720},
    {"kind": "marker",     "name": "AmpR", "length_bp": 861},
    {"kind": "terminator", "name": "B0015", "length_bp": 129}
  ],
  "logic_graph": {                  // EXTENDED — drives LogicCircuitView
    "genes": [{"name": "IL6", "role": "trigger", "state": "ON", "direction": "up"}],
    "mid_gate": "OR",
    "outer_gate": "AND",
    "invert": true,
    "output": "GFP",
    "caption": "IF A AND (B OR C) AND NOT D → EXPRESS GFP"
  }
}
```

`kind` is a stable vocabulary; **colours stay in the frontend** — that is presentation,
not science.

### 7.2 Extend the `default-v1` scoring profile

Add `gc_content`, `dynamic_range`, `predicted_success_rate`. Keep the existing six. The
mockup's `offTarget` is our `orthogonality` — a display-name mapping, not a new metric.

Because the UI renders metrics from data ([§2.5](#25-the-mockup-hardcodes-its-metric-list)),
adding metrics needs **no frontend change** beyond a display-name entry.

### 7.3 `MockEngine` fills all of it

Deterministically, as it already does. This is exactly what the mock is for: the whole
results explorer becomes demonstrable now, and Step 5 swaps the numbers for real ones
without touching a line of React.

> These changes touch `src/engine/` and `engine.contract`. The boundary test still applies
> — the frontend reaches them only through the API.

---

## 8. Screens the design does not have

The mockup was drawn for a demo, so it omits everything unglamorous. Each of these is
required for the product to actually function:

| Screen | Why it is needed | Effort |
|---|---|---|
| **Login** | Every endpoint except `/health` and `/version` requires a session | S |
| **Run progress** | Runs are asynchronous. Without this the product appears frozen for the entire computation | **M — highest priority** |
| **Project list / "My Circuits"** | The nav button exists; the page does not | S |
| **Project detail** | Dataset history, run history, re-run | M |
| **Run failed** | `status=FAILED` with `error_summary`. The failure path is as much a product feature as the success path | S |
| **Run cancelled** + cancel button | Backend supports cooperative cancellation; no UI for it | S |
| **Dataset invalid** | `validation_report.errors` must be shown, or the user cannot fix their file | S |
| **Empty states** | No projects / no runs / no candidates after filtering | S |
| **Rejected candidates** | The DB *guarantees* every rejected candidate has a reason; the mockup shows only winners | S |
| **Annotations** | Backend fully supports pin/shortlist/synthesize + notes; no UI at all | M |
| **Use Cases page** | Nav item with no content anywhere in the export | Needs content from you |

### The progress screen, specifically

`GET /api/runs/{id}` returns `status`, `stage` (human-readable, meant to be displayed
verbatim), `progress_pct`, and `counts`. A 3-second poll that stops on a terminal status
is all that is needed. The mockup's mint progress bars and `StepRail` styling can be
reused directly — the visual vocabulary is already there, it just was never connected to
a running job.

---

## 9. Build order

Each sub-step leaves the app working. Run `./do dev` + `./do worker` throughout.

| # | Sub-step | Outcome |
|---|---|---|
| **4a** | **Vendor & de-SSR.** Copy `synth-logic-builder-main` → `frontend/`. Strip Start/nitro/wrangler/Cloudflare. Hand-write `vite.config.ts`. `main.tsx` SPA entry. Node **inside WSL** first. ADR 0005 | `npm run dev` shows the mockup at :5173, unchanged |
| **4b** | **Django serving.** `base: "/static/app/"`, build → `src/static/app/`, SPA catch-all in `config/urls.py`, `./do build-frontend`, Whitenoise | The mockup loads at `localhost:8000`, same origin |
| **4c** | **API client + auth.** `api/client.ts` (CSRF bootstrap, credentials, error envelope), types generated from `/api/openapi.json`, react-query provider, `/login`, route guard | Real login; `/api/auth/me` drives the nav avatar |
| **4d** | **Decompose.** Split `index.tsx` into `components/` + `routes/` per §5. No behaviour change | Same pixels, reviewable files |
| **4e** | **Wizard → real submission.** Project selector, upload → `POST /datasets` with validation report, logic + payload + mechanism forms, `POST /runs` → **redirect to `/runs/:id`** | A run appears in Django admin, the worker executes it |
| **4f** | **Progress + results.** Polling progress screen; `Step4` fed by `useCandidates`/`useCandidate`; metric-agnostic `MetricGrid`; client-side precision filters; rejected-candidate view; artifact download; CSV/xlsx export | **The milestone: full workflow in the browser on mock science** |
| **4g** | **Fill the gaps.** Project list/detail, failure + cancel + empty states, annotations UI, `/guide`, `/about`, `/use-cases` | Shippable |

Backend work from §6 and §7 slots in just before the sub-step that needs it: §6.2 items
1–5 before **4e**, §7 before **4f**.

**Suggested stopping point for review: end of 4f.**

---

## 10. Testing

Deliberately light — this is a UI for a few dozen users, and rule 12 applies.

| Layer | Approach |
|---|---|
| Backend additions | pytest, as in Steps 2–3. Non-negotiable: the new input mode, the config schema, xlsx/tsv parsing |
| Engine additions | Extend `tests/engine/test_mock_engine.py` — determinism must still hold for the new `design` fields |
| Frontend | **No unit test suite.** `tsc --noEmit` + `eslint` in `./do lint` |
| Integration | One Playwright smoke test through 4f's workflow — *if* it earns its keep. Otherwise the existing `tests/e2e/test_full_workflow.py` already covers the API path |
| Manual | A checklist in `docs/development.md`: login, upload good file, upload bad file, submit, watch progress, cancel, inspect candidate, download, export |

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| **De-SSR is fiddly.** `@lovable.dev/vite-tanstack-config` hides plugin wiring; unpicking it may fight TanStack Router's generated route tree | Timebox 4a. Fallback: drop TanStack Router for `react-router-dom` — the components do not care |
| **Windows Node.** `npm` resolves to `/mnt/c/...`; Vite across the WSL boundary is slow and produces path bugs | Install Node via nvm **inside WSL** before touching `frontend/`. [§15](software-design.md) |
| Tailwind v4 + oklch + `@theme inline` is new syntax | It already works in the export. Do not "modernise" `styles.css` |
| Design/engine data model drift | Metric-agnostic rendering (§2.5); everything scientific comes from the API |
| Node toolchain becomes an install prerequisite | `./do dev` serves the last committed build; only frontend work needs Node |
| `xlsx` npm package for export is unmaintained upstream | It is export-only, client-side, on data the user already has. Acceptable; revisit if it breaks |

---

## 12. What still waits for Step 5

- Real sequences, folding energies and leakage predictions (mock values render identically)
- GenBank export — needs a real annotated construct
- CRISPR and antisense mechanisms — advertised via `/api/version`, shown as unavailable
- Off-target screening against a genome
- Plasmid segment lengths reflecting real payloads

**None of these block Step 4.** With §7 done, `MockEngine` produces everything the UI
renders, so the entire product can be demonstrated end to end on mock science — which is
precisely what the boundary in [§3](software-design.md) was built to buy.

---

## 13. Housekeeping

- Move `uploads/synth-logic-builder-main/` → `frontend/`
- Keep `*.dc.html`, `guide-shots/`, `screenshots/`, `CERNAL_Overview.md` as design
  reference — suggest `docs/design-reference/`
- Discard `diagrams.jsx`, `support.js`, `image-slot.js` (design-canvas runtime),
  `uploads/iGEM_Wiki_Test-main/` (separate project), all `*:Zone.Identifier`
- Decide whether `uploads/*.pptx` and team photos belong in the repo or in the wiki
- `lovable_frontend_raw/` should not survive Step 4 as a top-level directory
