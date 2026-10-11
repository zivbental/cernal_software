# Final supported payload matrix — 2026-10-08

At source commit `24280ec0aab6e89372048658f07cf72f8e1f9a6d`, all 12
single-input toehold jobs completed successfully with all 54 host-applicable output
alternatives accepted. There were zero empty jobs, failures or exceptions. Total wall
time was 322.345 seconds with two concurrent workers and a 600-second overall limit.

| Host | Direct accepted / candidates | DE accepted / candidates | Gene accepted / candidates |
| --- | --- | --- | --- |
| ecoli | 6 / 6 (63.851 s) | 6 / 6 (61.708 s) | 6 / 6 (62.911 s) |
| yeast | 4 / 4 (51.425 s) | 4 / 4 (46.341 s) | 4 / 4 (48.043 s) |
| human | 4 / 4 (49.647 s) | 4 / 4 (49.292 s) | 4 / 4 (51.413 s) |
| c_acnes | 4 / 4 (47.709 s) | 4 / 4 (47.784 s) | 4 / 4 (49.314 s) |

E. coli alternatives were GFP, mCherry, firefly luciferase, AmpR, KanR and custom;
other hosts used GFP, mCherry, firefly luciferase and custom. Each job retained one
gate (budget 1), used no backbone, selected assembly standard `none`, retained default
scoring hard filters and disabled optional codon optimization. The environment was the
fresh final venv; engine `local-0.11.0-scientific-qa`, profile
`v3-computational-proxies`, ViennaRNA 2.7.2 at 37°C, seed 42.

All artifact checksums were verified. The 108 export audits returned `HOLD_SYSTEM`
with `release_allowed=false`; no FASTA/GenBank/SBOL sequence exports were created.
No screening adapter was bypassed.

DE contrasts are synthetic fixtures over pinned reference genes. Gene mode resolves
one pinned gene; this is not an arbitrary gene-list compiler. The results establish
computational integration, not expression, clinical classification, molecular activity
or calibrated efficacy. No AND/NOT/CRISPR/apoptosis implementation or multi-input
truth-table claim is made. Timing is an observation under concurrent root regression
load and does not establish a worst-case runtime guarantee.

The [JSON evidence](final-payload-matrix-2026-10-08.json) retains per-case effective
constraints, input/reference checksums, model versions, raw metrics, payload/source and
construct digests, stage times, warnings, artifacts and release decisions. The exact
[executed harness](final-payload-matrix-harness-2026-10-08.py.txt) is archived as text;
its SHA-256 is recorded in the evidence. It uses fixed QA workspace paths and can be
executed with Python after adapting those paths. No frozen publish source was edited.
