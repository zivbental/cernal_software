# Bacterial AND development measurements

The `region-input-*` records below exercise the corrected compiler. The other
archives preserve earlier development models and do not validate its current
contract. See the scope correction in
[the historical record](../prokaryotic-and-pipeline-2026-10-18.md); old commands must
be run at their producer revision. Previously archived bytes remain unchanged.

These small, compressed JSON records preserve the actual development measurements
used to assess pair selection and output-context cost. `checksums.json` gives both
compressed and original SHA-256 digests. Decode with Python's `gzip` module; no
scientific dependency is needed to inspect them.

The corrected production examples are `region-input-gfp-20.json.gz` and
`region-input-gfp-160.json.gz`. Both used the same upstream 100 regions across
`ggt`/`astC`, discovered 86 ordered compatible pairs and carried the top 8. They
evaluated 20 and 145 switches respectively (23 and 160 attempted assemblies),
accepting none; all rejections and four-state diagnostics were retained. Elapsed
times were 50.608 and 220.579 seconds on this Windows machine with concurrent test
processes, not controlled performance comparisons. The second record's producer
core hashes match the committed correction; the first precedes the unrelated
non-AND call-shape fix. Neither result establishes useful production yield or
biological function. A real historical positive separately passes the switch-only
22-check regression test; it was not selected by these bounded upstream-pool runs.

Re-run the current example from the repository root:

```console
uv run --locked --extra dev python tools/pair_budget_on_pfas.py --pipeline --pipeline-output gfp --seed 7 --max-designs 160 --max-pairs 8 --run-dir var/and-region-input-gfp-expanded --out var/and-region-input-gfp-expanded.json
```

The remaining records below preserve earlier development models; their historical
commands and conclusions must not be substituted for this production contract.

They were produced from integration baseline `e7d675e` plus working-tree changes.
Each record explicitly marks that fact and, where available, records producer-file
hashes. They are development snapshots, not a claim that checking out the baseline
alone reproduces the changed implementation. The portable current commands and
complete application example are documented in
[the integration evidence](../prokaryotic-and-pipeline-2026-10-18.md).

- `prokaryotic-and-pair-discovery.json.gz`: candidate counts and upstream profiling.
- `prokaryotic-and-pilot.json.gz`: the alternative minimum-per-base ordering pilot.
- `prokaryotic-and-mean-pilot.json.gz`: the weaker-window mean ordering pilot.
- `prokaryotic-and-contexts.json.gz`: the same selected historical positive switch
  evaluated alone, with a short custom output, and with complete GFP RNA.
- `prokaryotic-and-compiler-*.json.gz`: complete application-path examples before
  and after rotated grid ordering, including a GFP full-context rejection.
- `window-audit.json.gz`: ON opening costs over 30 and 31 nt for the 77 Green
  single-input switches with measured ON/OFF above 20.

The historical positive was selected as a regression control. It is not evidence
that the default search selected it. Complete-pipeline examples separately test
un-pinned pair discovery and selection. Timings describe this Windows machine and
model, not guaranteed runtimes. All 22 structural thresholds remain unchanged.

The context comparison is consequential: the 161-nt switch passed all 22 checks
in 1.926 seconds; the 170-nt short-output transcript passed in 2.448 seconds;
the 878-nt full GFP transcript took 116.587 seconds and failed `A_M_11 > 0.5`.
Those are computational structural predictions and demonstrate context dependence.
The assistant-added mandatory full-CDS verification was subsequently removed to
restore the team's declared folding boundary. The comparison does not establish
that the full-CDS context is more accurate.

The coordinate audit found maxima 7.048805 kcal/mol over the engine's 30-nt
`span(-17,13)` and 7.204948 over the legacy calibration's 31-nt slice. The 7.2
ceiling remains unchanged and admits all 77 in the 30-nt recheck; it must not be
described as that cohort's exact maximum. Source Table S1 SHA-256:
`1c47d155ab0cebbd4693544b7db8bfa72059b64213fa422a7f438f2be0dc3fec`.
This audit evaluates the supplied single-input switch/trigger context, not a full
reporter CDS or the bacterial AND mechanism. The producer worksheet remains an
external input; the stored JSON is the complete measured numeric audit record.

Large historical sweeps remain outside Git and need a separately verified archive
with inputs, producer versions and checksums. These records do not resolve the
historical PFAS input provenance or reproduce all Wiki figures. Corrected barrier
data retain their existing provenance under `docs/assets/barrier/`; no barrier is
used by the bacterial application compiler.
