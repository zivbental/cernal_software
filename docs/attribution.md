# Attribution

**CERNAL — Compiler-like Engine for RNA Logic.** iGEM 2026, Tel Aviv University.

This file is the source of truth for the iGEM **Attribution Form**. It records who did
the work, which third-party components CERNAL builds on, and how AI tools were used —
the last being a requirement of iGEM's 2026 [Policy on the Responsible Use of Artificial
Intelligence](https://igem.org/legal?tab=ai-policy-teams), §4, *Disclosure Through the
Attribution Form*.

> Lines marked **`TODO`** can only be answered by the team. Fill them in before the
> Attribution Form is submitted and before the GitLab freeze — after the freeze this
> file cannot be changed.

---

## 1. Human authorship

CERNAL was designed and built by the iGEM 2026 Tel Aviv University team.

| Area | Who |
|---|---|
| Software architecture, backend, API | `TODO` |
| Scientific engine design | `TODO` |
| Frontend implementation | `TODO` |
| Scientific direction (RNA logic, gate chemistry, scoring) | `TODO` |
| Principal Investigator | Prof. Tamir Tuller, Tel Aviv University |
| Advisors / outside help | `TODO` — anyone outside the student team who contributed |

Work done by people outside the team — a lab member who supplied a dataset, a
postdoc who reviewed the folding model, an alum who set up the runner — belongs here.
iGEM asks specifically about outside help, and omitting it is the common failure mode.

## 2. AI-assisted work

AI tools were used in building CERNAL. Under iGEM's policy this is permitted; what is
required is that the use is disclosed, that the tools are reported **as tools and not as
contributors**, and that the team can explain and has verified the output.

### What is verifiable from this repository

| Tool | What it produced | Where it landed |
|---|---|---|
| [Lovable](https://lovable.dev) | The original React/TypeScript design and component library — visual language, layout, the shadcn/ui + Tailwind component set | `frontend/`, via the export preserved in [design-reference/](design-reference/). See [ADR 0005](decisions/0005-static-spa-not-tanstack-start.md) for what was stripped and rewritten by hand |
| AI coding assistant | `TODO` — name the tool(s) and describe the scope: which of the backend, engine scaffold, tests and documentation were AI-assisted | Repository-wide |

### What the team must be able to state

Under §5 of the policy, AI-assisted output must be independently reviewed and verified
before being incorporated. For this project that means, concretely:

- **AI-generated code was reviewed and tested.** The suite is 415 tests, and
  [`tests/test_boundary.py`](../tests/test_boundary.py) mechanically enforces the
  engine/Django separation rule. `TODO` — confirm the team reviewed the engine stubs
  and scoring logic rather than accepting them unread.
- **The science is the team's own.** The scientific stages, gate chemistry and scoring
  weights are the team's design decisions, not an AI's suggestions accepted at face
  value. `TODO` — confirm, and note anywhere an AI suggestion was adopted into the
  scientific design.
- **No fabricated results.** See §5 below.

AI tools are **not** listed as team members anywhere in this repository, on the wiki, or
on the Attribution Form.

## 3. Third-party software

Every dependency below is under a permissive, OSI-approved license compatible with
CERNAL's own Apache-2.0 license. Versions are those resolved at the time of writing; the
authoritative pins are [`uv.lock`](../uv.lock) and
[`frontend/package-lock.json`](../frontend/package-lock.json).

### Python — runtime

| Package | License |
|---|---|
| Django | BSD-3-Clause |
| django-ninja | MIT |
| django-q2 | MIT |
| django-environ | MIT |
| openpyxl | MIT |
| whitenoise | MIT |
| gunicorn | MIT |
| pydantic / pydantic-core | MIT |
| asgiref, sqlparse | BSD |

### Python — development

pytest (MIT), pytest-django (BSD-3-Clause), ruff (MIT).

### JavaScript / TypeScript

| Package | License |
|---|---|
| React, React DOM | MIT |
| TanStack Router, TanStack Query | MIT |
| Radix UI (27 primitives) | MIT |
| shadcn/ui — component source vendored into `frontend/src/components/ui/` | MIT |
| Tailwind CSS | MIT |
| Recharts, Zod, react-hook-form, date-fns, sonner, vaul, cmdk, embla-carousel | MIT |
| lucide-react | ISC |
| class-variance-authority, SheetJS (`xlsx`), TypeScript, Playwright | Apache-2.0 |
| Vite, ESLint and the build toolchain | MIT |

No GPL, AGPL or other copyleft dependency is present in either tree.

### Scientific dependency — not OSI-approved

**ViennaRNA** is planned as the engine's RNA folding backend
([deployment.md](deployment.md), [engine.md](engine.md) — `FoldEngine`). Its license is a
custom one: free for research, education and commercial use, but it **forbids
redistribution for a fee** and is **not OSI-approved**.

This does not affect CERNAL's own license, but it constrains distribution:

- ViennaRNA is a dependency the user installs — CERNAL does not vendor or redistribute
  it, and any published container image must not bundle it while being described as
  wholly open source.
- The dependency and its license must be stated on the wiki's software page alongside
  the claim that CERNAL is open source.
- All ViennaRNA calls are funnelled through one module so the backend can be swapped;
  that boundary is the mitigation if an OSI-licensed alternative becomes preferable.

## 4. Design assets

| Asset | Origin | License / permission |
|---|---|---|
| CERNAL logo (`frontend/src/assets/cernal-logo.png`, `cernal-logo-animated.svg`) | `TODO` — team-designed, or generated? | `TODO` |
| UI iconography | lucide-react | ISC |
| Team photographs | Team members | `TODO` — confirm every person pictured consented to publication |
| Design mockups in [design-reference/](design-reference/) | Lovable | See §2 |

`TODO` — if **any** image, font, illustration or diagram anywhere in the project was
downloaded rather than made by the team, it needs its source and license recorded here.
iGEM's communication rules apply to the wiki and to this repository alike.

## 5. Data

**The bundled example dataset is illustrative, not experimental.**
`src/apps/datasets/examples/ecoli_oxidative_stress.csv` is shipped so that CERNAL can be
evaluated without the user supplying their own differential-expression results.

`TODO` — **resolve before the freeze.** The dataset is currently described in
`src/apps/datasets/services.py` as "50 genes from a differential-expression analysis",
with no accession or citation. Either:

1. record the source here and cite it (GEO/SRA accession, publication), if the values
   were taken from a real experiment; or
2. relabel it explicitly as a **synthetic illustrative dataset** in both that
   description string and the user interface.

iGEM's AI policy §6 is unambiguous: simulated or generated material may be used, but it
must be *clearly distinguished* from real observations and must never be represented as
a result the team obtained.

**Mock engine results are simulated.** With `CERNAL_ENGINE=engine.client.MockEngine`
(the default), every number the product displays is deterministic fake output. The
application labels this in the footer — "Mock engine — results are simulated" — but
**screenshots do not carry that label**. Screenshots taken against MockEngine, and the
mockup screenshots in `design-reference/guide-shots/`, must not appear on the wiki
presented as results.

## 6. Personal data

CERNAL stores account details (username, email address, full name) and whatever
transcriptomic files users upload. Accounts are approved manually by a staff member;
there is no email delivery and no third-party analytics.

`TODO` — if CERNAL is deployed publicly for the Jamboree, decide and record: who
controls the data, how long uploads are retained, and what happens to accounts after the
competition. If a user could upload human transcriptomic data, that is a privacy
consideration for a Tel Aviv University-hosted deployment and is relevant to the iGEM
safety form.

---

## Checklist before the GitLab freeze

- [ ] Every `TODO` above resolved
- [ ] This file's content transferred to the iGEM Attribution Form
- [ ] Wiki software page states the license, the repository URL, and the ViennaRNA caveat
- [ ] Example dataset either cited or relabelled as synthetic
- [ ] No MockEngine output published as a result
