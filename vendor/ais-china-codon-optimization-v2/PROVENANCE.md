# Provenance — this directory is not ours

Everything under this directory except this file is the work of the **iGEM AIS-China
2026 team**, copied here **byte-for-byte and unmodified**.

| | |
|---|---|
| Upstream | https://gitlab.igem.org/2026/software/ais-china/codon-optimization-v2 |
| GitHub mirror (stale; does **not** contain the commit below) | https://github.com/LTYyy17/c-acnes-codon-optimization-version2 |
| Commit | `e8a57cf1b5696ed7b3931f6b63ea49afbc5ccbf9` |
| Commit date | 2026-10-03 |
| Upstream version | 2.0.1, reference package `2026-09-06.v1` |
| License | Apache-2.0 (see `LICENSE`) |
| Modifications by CERNAL | **None.** Not a single byte of their files was changed — not formatting, not line endings (their files are CRLF and stay CRLF), not lint fixes |
| Files vendored | 84 |
| Recursive content SHA-256 | `fa75b595515c943bb855de1574cf8a66589205f66421c3e57eaf5a58224239c2` (over all files except this one, at the time of vendoring) |

Used with the written permission of the AIS-China team. Apache-2.0 §4 permits this
redistribution; §4(b) requires a statement of changes, and the statement is that there
are none.

## Why this is vendored and not a git submodule

It **was** a submodule, pinned at the same commit (PR #43). On 2026-10-07
`gitlab.igem.org` began returning HTTP 503, and the consequences were immediate and
total: `main`'s CI failed at `actions/checkout` before running a single test, a fresh
clone of CERNAL could not be built or tested at all, and any deployment that clones the
repository would have failed the same way. Their own GitHub mirror was not a fallback —
it was last pushed 2026-09-06 and does not contain the commit above.

A submodule makes every clone, every CI run and every deploy depend on a third party's
git host staying up. For a dependency this small, and for a project with a competition
deadline, that is the wrong trade. Vendoring removes the dependency entirely and makes
the exact bytes part of CERNAL's own history, which also makes reproducibility stronger
than a pointer to a mutable remote.

## What was taken, and what was not

Vendored, because the library needs it at runtime:

- `codon_v2/` — the library itself
- `config/` — frozen models, defaults, the motif automaton, the ViennaRNA energy parameters
- `data/hosts/` — the reference packages for **both** strains. Both are required even
  though CERNAL only exposes ATCC 6919: their `ReferenceStore.__init__` iterates every
  host declared in `config/defaults.json` and builds a `HostReference` for each, and we
  do not edit their config
- `docs/` — their algorithm and data documentation, which is the provenance for every
  number their code produces
- `LICENSE`, `README.md`

Not vendored, because nothing in CERNAL reads it: `data/raw/` (13 MB of genome archives
for their offline rebuild pipeline), `public/`, `reports/`, `web/` (their Flask UI and
its assets), `dev/`, `scripts/`, `tests/`, `examples/`, `app.py`, `wsgi.py`,
`vercel.json`, and their `CLAUDE.md`. Omitting a file changes no file; every file present
here is identical to upstream.

## If you need to update it

Do not edit anything here. Re-copy from upstream at a new commit, update this file, and
re-run `tests/engine/test_ais_china_energy_model.py` — that test is what guarantees their
ViennaRNA energy parameters still match the ones `FoldEngine` folds with. If it fails
after an update, the update must not be merged: a second energy model inside the process
would put `gate_folding_energy` on an axis that no longer matches
`FoldEngine.versions()`.
