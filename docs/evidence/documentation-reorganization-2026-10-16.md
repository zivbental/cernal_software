# Documentation reorganization verification — 16 October 2026

> Historical snapshot: PRs 68/69/81/82 have since merged. See [current status](../status.md) for accepted scope and CI receipts; original findings below are preserved.

Baseline main: `c1bb92cc085a6bad272298b81bda28c22b1d57f5`.
Documentation branch: `docs/igem-final-organization-2026-10-16`.

## Scope and outcome

Reorganized the documentation into current overview/tutorial, concepts/methods, API/client,
configuration/install/deployment/security, testing, evidence, limitations and contribution paths.
Removed contradictory scaffold/pending-merge claims from active guidance. Historical plans,
audits and original guide text remain byte-for-byte in a clearly separated archive.

Current scope is pinned to main; open PRs and IBBIS are explicitly branch-only. No feature
branch was merged, no PR was created, and no application deployment or sequence release
was performed. Runtime behavior, scientific numerical results and datasets were not changed.
The only existing non-Markdown edit is `.env.example` comments; its non-comment values are
identical to baseline. A new documentation link-check utility is isolated under `docs/tools/`.

## Executed checks

Environment: cloud Linux, CPython 3.13.5, Node 24.19.0, npm 11.9.0; Python dependencies
installed with `uv sync --locked --extra dev`, frontend dependencies with `npm ci`.
Temporary writable uv/npm cache locations were used; project lockfiles are unchanged.

| Check | Result |
|---|---|
| `ruff check .` and `ruff format --check .` | Passed; [log](documentation-checks-2026-10-16/ruff.txt) |
| `python manage.py check` | Passed, no issues |
| `python manage.py makemigrations --check --dry-run` | Passed, no changes |
| `python tools/gen_api_surface.py --check` | Passed: 68 modules, 381 callables; generated surface unchanged |
| `pytest -q` | **2,500 passed, 1 failed, 1 skipped, 110 subtests passed**, 694.75 s; [log](documentation-checks-2026-10-16/backend.txt) |
| Documentation/API-inventory/boundary focused rerun | **164 passed**, 1.12 s; [log](documentation-checks-2026-10-16/focused.txt) |
| Scientific focused check | **82 passed**, 2.79 s (trigger ranking, gate-aware triggers, folding configuration and genes); overlaps the full suite, not an additive total |
| `npm --prefix frontend run build` then `run check` | Passed: production build, TypeScript/lint, SSR/help/link and RNA adapter contracts; [log](documentation-checks-2026-10-16/frontend.txt) |
| `npm --prefix frontend run test:clean-build` | Passed from route-tree-absent state; verifies generation and rejection of injected TypeScript error; [log](documentation-checks-2026-10-16/clean-build.txt) |
| `python docs/tools/check_links.py` | Passed for active Markdown links/anchors, including root, CLAUDE, client and notebook entry points |
| `git diff --check` | Passed |
| Preservation inventory | All **765** original tracked files accounted for; every preserved SHA-256/size matched baseline Git objects |
| Markdown rendering | 66 active root/docs Markdown pages rendered to HTML and parsed without error; graphical browser inspection unavailable |

Focused command: `pytest -q tests/test_documentation_contract.py tests/test_api_surface_is_fresh.py tests/test_boundary.py`.
The full run started while documentation was being edited; the focused documentation rerun,
frontend checks, lint and link validation were repeated after the relevant final changes.
Runtime source was unchanged throughout. These checks are software verification, not biological validation.

## Known baseline failure

`tests/engine/test_contract.py::test_contract_types_are_frozen` assigns `kind` on
`MetricValue`, which has no such field. On this Python runtime the frozen/slots assignment
raises `TypeError`; the test expects `dataclasses.FrozenInstanceError`. Running that exact
test against the untouched baseline reproduced the same failure in 0.12 s:
[baseline reproduction](documentation-checks-2026-10-16/baseline-failure.txt).
No runtime/test alteration was made to hide or fix it. The full suite is **not all green**.
The skip is the native-Windows CLI regression on Linux.

## Readability and review boundaries

An independent source/diff review checked capability claims, current-versus-historical
navigation, links and preserved bytes. Findings about cache migration, old branch instructions,
MockEngine references, API anchors and client examples were corrected and reinspected.
The final review found no additional must-fix content/navigation issue.

Local headless Chromium screenshot inspection could not run because the sandbox denied the
browser's socket initialization; an allowed escalation path also failed to initialize its
wrapper. No visual screenshot sign-off is claimed. HTML rendering and frontend SSR/help
checks passed. Historical original relative links retain their original directory context;
use the inventory's immutable baseline links to read them. They are intentionally excluded
from the active-guide link check rather than silently rewriting historical evidence.

## Remaining alignment and human decisions

[Branch audit](branch-audit-2026-10-16.md) and [status](../status.md) pin all four open PRs
and relevant branch heads. Reconcile AND capability/API/help changes only after integration;
restore or explain missing canonical barrier rows before reproducible numeric publication;
validate real IBBIS executable/database behavior and reconcile its frontend/backend contract
before operational activation. NucSyn publication is not proof of CERNAL integration.

Public hosting, dedicated iGEM GitLab pipeline evidence, MATLAB runtime validation,
experimental efficacy, attribution/asset permissions and human-data governance remain scoped
as documented in [release decisions](../release-decisions.md). No external-site access,
production acceptance or new experimental result is inferred from this documentation work.

See [source inventory](documentation-inventory.md) and [baseline manifest](baseline-file-manifest.json).
