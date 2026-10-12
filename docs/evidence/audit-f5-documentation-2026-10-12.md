# F5 documentation verification — 2026-10-12

Baseline: `2baa75a7f0dc89f9aafac58dad50da5982f3f56a` (fresh isolated clone of main).

## Before and after

At baseline, README Current state and A note on results claim that removed
`MockEngine` is the default and all results are fake. The license section calls
ViennaRNA planned. `src/config/settings/base.py` and `.env.example` instead select
`engine.client.LocalEngine`; `pyproject.toml` and `uv.lock` include ViennaRNA.
The README now follows those sources and documents locked dependency installation
and explicit fresh frontend installation/route generation before typechecking.

The in-app metric chart formerly described success as confidence of behavior in vivo
and dynamic range as predicted expression fold change. The corrected chart and guide
state the actual proxy definitions and calibration limits. No numerical computation,
filter, score weight, checksum, release policy or engine version is changed.

Reproduce the baseline text with:

```bash
git show 2baa75a7f0dc89f9aafac58dad50da5982f3f56a:README.md
git show 2baa75a7f0dc89f9aafac58dad50da5982f3f56a:frontend/src/components/docs/MetricsChart.tsx
```

## Integration boundaries checked read-only

GitHub pull request API responses on 2026-10-12:

| Item | Observed state | Exact head |
|---|---|---|
| [PR 68](https://github.com/zivbental/cernal_software/pull/68) | Open, unmerged; eukaryotic single/AND research reports | `15b3842d40869ea7e152f954d3b79eeca1205314` |
| [PR 69](https://github.com/zivbental/cernal_software/pull/69) | Open draft, unmerged; frontend screening contract/UI only | `2d50e23cc75c3fee151ccb0524ab36e389dc8069` |

No code from either PR was imported into this documentation branch.
Windows operational documentation is owned by the separate F1 worker; README scopes
the application quickstart to Linux/WSL2 because locked Django Q2 requires `fork`.

## Dedicated iGEM software hosting remains unverified

`git remote -v` identifies this GitHub repository. A tracked-source search for
`gitlab.igem.org` finds the AIS-China codon-optimization collaboration URL in
`docs/collaborations.md`, not a dedicated CERNAL software project. `.gitlab-ci.yml`
is configuration, not proof of a hosted project or a successful GitLab pipeline.

Public read-only discovery of `https://gitlab.igem.org/2026/software` returned 403
through the web tool; `https://gitlab.igem.org/explore/projects?name=cernal` was
inaccessible. Search results supplied no verifiable CERNAL project. This does not
prove that a private or unindexed project does not exist.

**Exact missing input:** the team's authoritative dedicated software project URL
(including year/group/namespace/project, or its GitLab project ID), a readable source
commit corresponding to the reviewed GitHub revision, and the pipeline URL/status
for that exact commit. If private, a maintainer-provided read-only export or evidence
is sufficient for further checking; no new access or repository was created here.
The separate wiki repository was not edited.

## Verification

On the Work PC, with locked dependencies in this isolated checkout:

- New `tests/test_documentation_contract.py` copied to a detached baseline worktree:
  **2 failed, 1 passed** (obsolete README default and overly broad leakage description).
- Corrected checkout: documentation, boundary and complete toehold tests:
  **269 passed** (`pytest tests/test_documentation_contract.py tests/test_boundary.py
  tests/engine/gates/test_toehold.py -q`).
- `ruff check .`, `ruff format --check .`, Django system check, frontend `build:fast`,
  `check` and `build`: passed. Help checks render three pages, validate 37 links and
  seven negative controls, and now assert metric interpretation limits.
- Local native Windows execution required tool escalation for the installed Python
  runtime and Vite filesystem access. No permission, dependency or check was weakened.

The PR records exact-head CI separately. Linux/WSL worker acceptance belongs to F1;
this task did not launch a worker or claim a native Windows application smoke pass.
These checks establish documentation/software behavior only, not biological validation.
