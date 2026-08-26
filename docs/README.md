# CERNAL documentation

**Compiler-like Engine for RNA Logic** — TAU iGEM. A researcher supplies a transcriptomic
signal, defines a biological objective, and receives a ranked list of candidate RNA logic
circuits with scores, metrics, sequences and downloadable artifacts.

---

## Start here

| If you want to… | Read |
|---|---|
| Understand how the system is put together | **[architecture.md](architecture.md)** ← the entry point |
| Know what is built and what is next | **[ROADMAP.md](ROADMAP.md)** ← the only place future work lives |
| Understand the biology the software computes over | **[modalities.md](modalities.md)** |
| Work on the scientific engine | **[engine.md](engine.md)** |
| Just run the thing | **[development.md](development.md)** |

## Everything

| Document | What it is |
|---|---|
| [architecture.md](architecture.md) | **The authoritative reference.** Boundary rule, repository layout, domain model, run state machine, API shape, configuration, rules for agents |
| [ROADMAP.md](ROADMAP.md) | Every future task, open scientific question and planned implementation. Status lives here |
| [modalities.md](modalities.md) | The four design axes — input mode, host organism, gate chemistry, output payload — in detail |
| [engine.md](engine.md) | The scientific engine: contract, design principles, stages, records, tools, gates, scoring, layout, testing |
| [domain-model.md](domain-model.md) | Field-level reference for the eight Django models |
| [api.md](api.md) | Endpoint reference for the 32 HTTP endpoints |
| [development.md](development.md) | Setup, everyday commands, testing, troubleshooting |
| [deployment.md](deployment.md) | Where it runs in production, and why that shape |
| [attribution.md](attribution.md) | Who did the work, what CERNAL builds on, and how AI tools were used. **The source of truth for the iGEM Attribution Form** — it has `TODO` lines only the team can fill in |
| [decisions/](decisions/) | Architecture decision records. Adding a service or splitting the repo needs one |
| [design-reference/](design-reference/) | The original Lovable design artifacts, kept for reference. **Not a specification** |

## Conventions for this folder

- **Future work goes in [ROADMAP.md](ROADMAP.md)**, not in a new planning document. Fourteen
  overlapping planning files is how the previous version of this folder happened.
- **Decisions with a cost go in [decisions/](decisions/)** as a numbered ADR. Adding a
  service (Redis, Postgres, Docker, S3) or splitting the repository requires one first.
- **If a change contradicts [architecture.md](architecture.md), update it in the same
  commit**, with the reason.
- Diagrams are Mermaid or ASCII, inline. They render on GitHub, in VS Code and in Obsidian
  without a build step.

## Elsewhere in the repository

| Path | What |
|---|---|
| `Design Maps/` | The original Obsidian vault — 21 canvases, the long-term north star. [architecture.md §17](architecture.md) indexes the ones worth consulting |
| `README.md` (repo root) | Quickstart only |
| `.env.example` | Every environment variable, documented, with safe defaults |
| `.gitlab-ci.yml` | The CI pipeline — backend lint/checks/tests and a frontend build. One of iGEM's three Project Software deliverables |
| `LICENSE` · `NOTICE` | Apache 2.0 |
