# Collaborations

This file records work CERNAL uses that was made by another iGEM team, on what terms, and
exactly which version. It is the source of truth for the collaboration section of the wiki
and for the iGEM Attribution Form.

## iGEM AIS-China — *Cutibacterium acnes* codon optimization

| | |
|---|---|
| **Team** | iGEM AIS-China (2026) |
| **Their repository** | <https://gitlab.igem.org/2026/software/ais-china/codon-optimization-v2> |
| **What it is** | `c-acnes-codon-optimization-version2` (`codon_v2` 2.0.1): host-specific codon references and optimization strategies for *Cutibacterium acnes* |
| **Their licence** | Apache License 2.0 (their `LICENSE`; the same licence as CERNAL's) |
| **Permission** | Given in writing by the AIS-China team to use their tool as a library, with credit to them |
| **Where it lives here** | vendored, unmodified, at `vendor/ais-china-codon-optimization-v2` (see its `PROVENANCE.md`) |
| **Pinned commit** | `e8a57cf1b5696ed7b3931f6b63ea49afbc5ccbf9` |
| **Reference version** | `2026-09-06.v1` |
| **Host** | *C. acnes* ATCC 6919 — RefSeq assembly `GCF_008728435.1`, accession `NZ_CP044255.1` |
| **Wiki collaboration page** | **PLACEHOLDER — Ziv to supply the iGEM wiki collaboration URL here** |

### What we use, and what is theirs

CERNAL uses their frozen ATCC 6919 reference data (codon frequencies, CAI weights, tRNA
data, reference coding sequences) and their `codon_v2.pipeline.optimize` entry point. The
strategies behind it — CAI maximisation, classic tAI, host-frequency sampling, codon
harmonisation, 5' RNA accessibility — are their design and their credit.

The adapter is `src/engine/gates/tools/ais_china.py`. It builds their `ReferenceStore`
with the vendored path as its `root` argument (a parameter of their API, which is why no
change to their code is needed), calls `optimize`, and converts their report into CERNAL's
conventions (RNA alphabet, 0-indexed half-open coordinates). It exposes ATCC 6919 only;
their configuration, which also declares *C. acnes* KPA171202, is left exactly as they
shipped it.

### Apache-2.0 §4(b): modifications

**CERNAL has made no modifications to the AIS-China work.** Every file under
`vendor/ais-china-codon-optimization-v2/` is byte-for-byte the content of the pinned
commit above, including its CRLF line endings. Because nothing was modified, no
"modified files" notices are required or present. This is enforced, not just stated:
`tests/engine/test_ais_china.py` fails if the vendored tree does not hash to
`VENDORED_TREE_SHA256`, which it does not if any file has
any tracked file changed, and `vendor/` is excluded from our linter and formatter so that
no tool rewrites it. Their `LICENSE` is preserved alongside their code, and the work and its
authors are credited in [`NOTICE`](../NOTICE). (Their repository ships no `NOTICE` file of
its own, and its `LICENSE` carries no filled-in copyright line.)

### One energy model

Their code loads its own ViennaRNA parameter file with `RNA.params_load()`, which is
process-global. This does not create a second energy model because that file is numerically
identical to the ViennaRNA 2.7.2 defaults CERNAL's `FoldEngine` uses (checked across all
8,059 lines; only the line endings differ).
`tests/engine/test_ais_china_energy_model.py` makes that a standing check: it asserts
their parameter file still matches the hash in their own `config/rna_model.json`, that
loading it leaves `FoldEngine`'s folds bit-identical, and that their ensemble calculation
equals `FoldEngine`'s. Any update to the vendored tree must keep it passing.

### Updating the pin

1. Re-copy the files from upstream at the new commit; do not edit any file.
2. `uv run pytest tests/engine/test_ais_china_energy_model.py tests/engine/test_ais_china.py`.
3. Update `PINNED_COMMIT` in the adapter, the commit and any changed reference version
   in this file, `VENDORED_TREE_SHA256`, the vendored `PROVENANCE.md`, and `NOTICE` —
   all in the same commit as the re-copied files.


## Why vendored rather than a submodule

This started as a git submodule pinned at the same commit (PR #43). On 2026-10-07
`gitlab.igem.org` began returning HTTP 503 and the cost was immediate: `main`'s CI failed
at `actions/checkout` before running a single test, a fresh clone could not be built or
tested, and any deploy that clones the repository would have failed identically. Their own
GitHub mirror was no help — last pushed 2026-09-06, it does not contain the pinned commit.

A submodule makes every clone, CI run and deploy depend on a third party's git host. For a
dependency this small, in a project with a competition deadline, that is the wrong trade.
Vendoring removes the dependency and puts the exact bytes in CERNAL's own history, which
makes reproducibility stronger than a pointer to a mutable remote.

Nothing about the attribution changes. Their code is still used unmodified, their licence
still travels with it, and the "no modifications" statement Apache-2.0 §4(b) asks for is
now machine-checked by a content hash instead of by `git status` — a stronger check, and
one that cannot silently skip when there is no `.git` to interrogate.
