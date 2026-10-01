# In-app user help: maintainer map

The user-facing help is authenticated React content, not a separate documentation site.
There is one source of truth for each page:

| App route | Source |
|---|---|
| `/use-cases` | `frontend/src/routes/use-cases.tsx` |
| `/guide` | `frontend/src/routes/guide.tsx` |
| `/faq` | `frontend/src/routes/faq.tsx` |

Shared help navigation and the warning treatment live in
`frontend/src/components/docs/HelpNav.tsx`. The authenticated shell and main navigation
live in `frontend/src/components/layout/AppShell.tsx`.

## Claim-to-source map

When behavior changes, update the help from implementation evidence rather than copying
historical summaries:

- engine default and upload limit: `src/config/settings/base.py`
- MockEngine determinism and LocalEngine scope: `src/engine/client.py`
- DE parsing, aliases, and numeric handling: `src/engine/inputs.py`
- upload formats and shallow validation: `src/apps/datasets/services.py`
- pipeline hosts, families, backbones, warnings, and artifacts: `src/engine/pipeline.py`
- platform-derived `summary.csv` and `manifest.json`: `src/apps/results/services.py`
- artifact listing, individual downloads, CSV export, and ZIP bundling:
  `src/api/routers/results.py`
- wizard modes and blockers: `frontend/src/routes/compile.tsx` and
  `frontend/src/components/compile/`
- result filters, failures, and downloads: `frontend/src/routes/runs.$runId.tsx` and
  `frontend/src/components/results/`
- frozen run metadata and execution: `src/apps/analyses/`
- ownership: `src/api/auth.py` and `src/api/routers/runs.py`
- account approval: `src/api/routers/auth.py`

## Validation

From `frontend/`, regenerate routes before TypeScript, then run:

```bash
npm run build:fast
npm run test:help
npm run check
npm run build
```

`npm run test:help` renders the actual help content with the existing esbuild/React SSR
stack. It checks required claims, prohibited false manifest claims, all same-origin
routes, rendered or source-evidenced fragment targets, duplicate IDs, placeholder and
unsafe URLs, immutable GitHub source-file links, and local file links in the root README,
docs index, this maintainer map, and the software development log. These checks remain
active in staged and clean CI checkouts. Historical source trees are checked when present;
shallow clones still validate the pinned revision and tracked local source targets.
Seven negative controls exercise bad routes, missing rendered and source-evidenced
fragments, unsafe schemes, malformed URLs, duplicate IDs, and nonexistent source paths.
It is part of `npm run check`; live external HTTP checks remain separate.

For browser verification, sign in with an approved account and visit `/use-cases`,
`/guide`, and `/faq` at desktop and narrow viewport widths. Follow the help navigation,
the guide table of contents, every cross-page fragment, API Reference, and New Circuit.
Confirm keyboard focus is visible and that the header/help links wrap without horizontal
page overflow. MockEngine output is UI test data, not scientific validation.
