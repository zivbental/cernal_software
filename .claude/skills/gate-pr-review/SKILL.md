---
name: gate-pr-review
description: "Review a pull request against this CERNAL engine repo and report what it changes and whether to merge it. Use when asked to review, assess, triage, or decide on a PR, given a PR number, a branch name, or nothing (current branch vs origin/main). Enforces the rule that a gate PR may only change gate family code (src/engine/gates/*.py) and gate notebooks (src/engine/gates/notebooks/), may only rarely and with written justification touch the shared gate tools (src/engine/gates/tools/, gates/base.py), and must change nothing else — any other change makes the recommendation REJECT."
---

# Gate PR review

Produce a written report for a pull request: **what it entails** and **whether to merge
it**. This project's PRs are expected to be gate work. The report's first job is a
**scope check**; only PRs that pass it get a full correctness review.

## 1. Get the PR

Take the argument as a PR number, a branch name, or empty.

- **PR number** — `gh pr view <n> --json title,body,author,headRefName,baseRefName,files,additions,deletions,url` for metadata, `gh pr diff <n> --patch` for the diff. To run the checks in section 5 you need a working tree: note the current branch, `git stash` if dirty, `gh pr checkout <n>`, and restore afterwards.
- **Branch name** — `git fetch origin <branch>` then diff `origin/main...origin/<branch>` (three dots = changes on the branch only).
- **Empty** — target the current branch: `git diff --stat origin/main...HEAD` and `git diff origin/main...HEAD`. `git fetch origin main` first so the base is current.

Get the full list of changed files with `git diff --name-status origin/main...<ref>`. Read every changed file (the new version, and the diff hunks for context) before writing the report — do not review from the diff alone.

## 2. Classify every changed file

Put each changed path in exactly one zone. The worst zone present drives the verdict.

### Zone A — In scope (the expected content of a gate PR)

| Glob | Notes |
|---|---|
| `src/engine/gates/toehold.py`, `antisense.py`, `crispr.py` | Existing gate families |
| `src/engine/gates/<new_family>.py` | A new chemistry — one new module is the normal way to add a gate |
| `src/engine/gates/registry.py` | **Only** an added `import` + `register(NewGate)` line. Any other edit here → Zone B |
| `src/engine/gates/__init__.py` | Only if it re-exports a new family |
| `src/engine/gates/notebooks/**` | Per-gate notebooks, `_fixtures.py`, `README.md` — "related notebooks" |
| `tests/engine/**` (new or extended) | Gate/tool test coverage. A gate PR *should* add tests |

### Zone B — Rare, needs written justification (shared across gates)

| Glob | Why it's sensitive |
|---|---|
| `src/engine/gates/tools/{binding,codons,folding,translation,__init__}.py` | Shared by every family. A change here can shift numbers `engine.scoring` normalises onto one axis — see engine.md §2.4, §3.4 |
| `src/engine/gates/base.py` | The `GateFamily` ABC. Changing the interface touches all four families |
| `src/engine/gates/registry.py` (logic, not a `register()` line) | Lookup/validation used by the API via `EngineCapabilities` |
| `src/engine/domain.py` — **only** a new `GateKind` enum member (and, if truly needed, a new `Host`) for a new family | Unavoidable for a genuinely new chemistry. **Nothing else in `domain.py`.** Flag it; the recommendation cannot be higher than "merge after a maintainer signs off on the enum addition" |
| `docs/modalities.md` §3, `docs/engine.md` §3.5, `docs/ROADMAP.md` gate rows, `Design Maps/Maps/12 Gate and Scoring Architecture.canvas` | Gate documentation kept in step with the code — acceptable, low severity |

Zone B is legitimate only when the gate work **cannot** be done without it. The PR (or its description) must say why. No justification → treat as a Major finding and REQUEST CHANGES.

### Zone C — Prohibited → REJECT

Anything not in A or B. In particular:

- `src/engine/stages/**`, `src/engine/scoring/**`, `src/engine/pipeline.py`, `src/engine/store.py`
- `src/engine/{contract,client,domain,sequences,artifacts,errors,__init__}.py` (except the one narrow `domain.py` case in Zone B)
- `src/apps/**`, `src/api/**`, `src/config/**`, `manage.py`, any `migrations/**`
- `frontend/**`, `src/static/**`
- `pyproject.toml`, `uv.lock`, `.gitlab-ci.yml`, `do`, `.env.example`, `deploy/**`
- **`tests/test_boundary.py`** — weakening this is the single worst change in the repo (architecture.md §3, development.md). Any edit that adds an exception → REJECT, no matter what else the PR does.

A non-trivial Zone C change means the report's verdict is **REJECT (out of scope)** and leads with that. Whitespace-only or comment-only Zone C touches: note them and ask for removal, but they need not sink an otherwise-clean PR.

## 3. Scope verdict

- Any Zone C change (beyond trivial) **or** a weakened boundary test → **REJECT**. Stop the correctness review; the report explains which files are out of scope and what a compliant PR would look like.
- Zone B changes without justification, or that break cross-family consistency → at best **REQUEST CHANGES**.
- Only Zone A (plus justified Zone B) → continue to section 4.

## 4. Correctness & conventions (Zone A / justified Zone B only)

Check against `docs/engine.md` and the gate docstrings. Report each finding with a
severity — **Blocker / Major / Minor / Nit** — a `file:line`, what is wrong, why it
matters, and a concrete fix.

**Gate family contract**
- New family sets every `ClassVar`: `name`, `version`, `kind`, `label`, `description`, `supported_hosts`, `max_inputs`, `available`. `register()` raises without `name`/`version` (registry.py).
- `version` is **bumped** whenever generation or evaluation output changes (base.py: "Bump `version` whenever generation or evaluation changes in a way that alters output"). Changed science + unchanged `version` → Blocker.
- `generate_designs` **yields**, never builds and returns a list (engine.md §3.5).
- `is_compatible` does **cheap checks only** — no folding, no `generate_designs` call. Its `Compatibility.no(reason)` text is shown to a researcher, so it must be plain language.
- `evaluate_design` returns **raw** values keyed by metric name — no normalising, weighting, filtering, or ranking (that is `engine.scoring`). Missing metric → `None`, never a sentinel like `-1`. Metric keys should line up with `engine/scoring/profiles.py` (`default-v1`).
- Tools (`FoldEngine`, `TranslationScorer`, `CodonOptimizer`, …) are received in `__init__` and **never constructed inside the gate** — the fold cache only helps if one instance is shared (engine.md §4 "Tools are constructed once per run").

**Engine-wide invariants**
- Imports point downward only: a gate may import `engine.domain`, `engine.sequences`, `engine.contract`, `engine.gates.tools`, `engine.gates.base`. It must **not** import `engine.stages`, `engine.pipeline`, `engine.scoring`, Django, `apps`, `api`, or `config` (architecture.md §3, enforced by `tests/test_boundary.py`).
- Determinism: same `seed` / inputs → identical designs and metrics. Flag unseeded `random`, set iteration order, dict-ordering dependence, timestamps in output.
- Failures are data; bugs are exceptions (engine.md §1.3). Expected scientific dead-ends return an empty iterator or `Compatibility.no(...)`; they don't raise. Programming errors propagate.
- Frozen data: any new record-like type is `@dataclass(frozen=True, slots=True)`. But new domain records belong in `domain.py` (Zone C) — a gate needing one is a design discussion, not a merge.
- No possessive or personal names in identifiers (engine.md §5: no "Aviv's generator").
- ViennaRNA (`import RNA`) stays behind `FoldEngine`; gate/notebook code must not import it directly.

**Notebooks** (`src/engine/gates/notebooks/`)
- A new family has a folder with a walkthrough named for the gate (`crispr/crispr.ipynb`), following the existing structure: mechanism markdown → `_fixtures` bootstrap cell → build → inputs → one section per gate method via `fx.attempt(...)`.
- Outputs are **stripped** and `execution_count` is `null` in every committed notebook (matches the four existing ones). Committed cell outputs → Minor.
- Notebook reads top-to-bottom today: scientific calls go through `fx.attempt(...)` so `NotImplementedError` prints `pending Step 5` instead of aborting.
- New shared fixtures added to `_fixtures.py` are also added to `__all__`.
- `_fixtures.py` and the notebooks are a manual workbench, not importable package code — nothing under `engine/` imports from `notebooks/`, and the folder has no `__init__.py`.

## 5. Run the checks

From the repo root, on the PR's working tree:

- `./do lint` — ruff check + format (line-length 100). Must pass.
- `./do test tests/engine` — gate/engine suite. Must pass; should stay under a second.
- `./do test tests/test_boundary.py` — the boundary. Must pass. A failure here is a scope violation even if section 2 missed it.
- `./do test` — full suite, if the PR touched Zone B or you want the belt-and-braces check.
- Notebook hygiene: for each changed `*.ipynb`, confirm every code cell has `outputs: []` and `execution_count: null`.

Record the actual command output (pass/fail + first failing lines) in the report. If checks can't be run (no working tree, missing deps), say so — don't guess.

## 6. Write the report

Markdown, to the terminal. Save a copy to the scratchpad dir and offer it via SendUserFile only if asked for a file.

```
# Gate PR review — <title>  (<#n | branch>)
<url if any>

## Verdict: <REJECT (out of scope) | REQUEST CHANGES | MERGE WITH NITS | MERGE>

<2–4 sentences: what the PR is trying to do, in gate terms, and the headline reason
for the verdict.>

## What it changes
- <plain-English summary of intent and the gate mechanism it implements/edits,
  grounded in the gate docstring / modalities.md §3 — not just a restatement of the diff>
- Files by zone:

  | Zone | File | +/- | Note |
  |------|------|-----|------|
  | A | src/engine/gates/toehold.py | +120 / -8 | fills generate_designs, evaluate_design |
  | ... |

## Scope check
- Zone A only? <yes/no>
- Zone B touched? <files + is the justification present and sufficient?>
- Zone C touched? <files — this forces REJECT> / none
- tests/test_boundary.py intact? <yes/no>

## Correctness & conventions
<one bullet per finding: [Blocker|Major|Minor|Nit] file:line — problem — why it
matters — fix. "No findings." if clean.>

## Checks
- ./do lint: <pass/fail + detail>
- ./do test tests/engine: <pass/fail + detail>
- ./do test tests/test_boundary.py: <pass/fail>
- notebook outputs stripped: <pass/fail per file>

## Recommendation
<Merge as-is | Merge after nits | Do not merge until: numbered list of required
changes | Reject and reopen as a scoped gate PR — here's what that looks like>
```

## 7. Verdict rubric

- **REJECT (out of scope)** — any non-trivial Zone C file, or a weakened `tests/test_boundary.py`, or the boundary test fails. Scope beats code quality: a flawlessly written PR that also edits `src/api/` is still REJECT.
- **REQUEST CHANGES** — in scope, but ≥1 Blocker or Major finding: unjustified Zone B change, `evaluate_design` doing scoring's job, `generate_designs` returning a list, `is_compatible` folding, a tool constructed inside a gate, non-determinism, missing `version` bump on changed science, `./do lint` or a test failing, a notebook that no longer reads top-to-bottom, personal names in code, a new `GateKind` without maintainer sign-off.
- **MERGE WITH NITS** — in scope, all checks pass, only Minor/Nit findings (committed notebook outputs, a docstring gap, a metric key that could align better).
- **MERGE** — in scope, all checks pass, no findings.
