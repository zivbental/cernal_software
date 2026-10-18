# Historical development measurements — superseded AND model (2026-10-18)

**Scope correction:** these measurements describe the earlier development model at
`679ea32`, before the maintainer clarified upstream-region inputs and the deliberate
switch-through-linker folding boundary. They do **not** validate the current compiler.
The current method is [documented here](../and-gate.md). Preserved context comparisons
show that changing the modeled RNA changes predictions; they do not establish that
full-CDS folding is more accurate or a required eligibility test. The associated raw
archives/checksums are preserved unchanged. Historical commands below must be run at
that historical revision, whose CLI still accepts `--full-finalists`.


The complete compiler was run on the bundled E. coli `ggt` (`b3447`) and `astC`
(`b1748`) references, supplied through a small differential-expression table. The
named genes were the inputs; no RNA windows, secondary stem, switch sequence or
positive result were pinned. Every run used seed 7, the shared equilibrium tools,
the existing 7.2 kcal/mol ON ceiling, all 22 structural checks, and the shared
scoring profile. Barrier calculations were disabled. These are computational
predictions, not measured expression or experimentally validated AND behavior.

The measured implementation used 8 top-ranked compatible pairs, 2 stems per pair,
at most 2,187 secondary-arm assignments per pair, at most 160 assembly attempts,
and 20 validated designs for screening. The compact grid has 5 closures × 2 upper3
choices × 2 lower3 choices. Generation interleaves pairs and stems and rotates the
balanced grid between pairs. Pair ranking uses the weaker window's **mean**
unpaired probability; each candidate's minimum per-base accessibility remains a
separate measurement.

| Complete compiler run | Seconds | Screened candidates | Screen passes | Full output attempted | Accepted and ranked |
| --- | ---: | ---: | ---: | ---: | ---: |
| Short custom CDS `ATGGCTGCTTAA`, rotated grid | 47.909 | 20 | 1 | 1 | 1 |
| GFP, rotated grid, one full-output finalist | 86.654 | 20 | 3 | 1 | 0 |

The custom CDS is a minimal software test output, not a functional reporter. Its
single admitted candidate passed all 22 checks with the full switch plus the
entire downstream output CDS. Its switch SHA-256 is
`f5091af7ea536abb853443c57523fe29b3044d43c556906d7f89d0efde0ba4ec`.
State `10` was the worst OFF state. The computation retained all 19 rejected
candidates and their reasons. The application wrote `candidates.csv`,
`and-search.json`, trigger provenance, and the HTML report. The real sequence
release policy remained active, so this measurement does not claim FASTA release.

The GFP run spent 32.943 seconds checking its selected full-output finalist. That
candidate's ON opening cost rose to 8.773 kcal/mol, above the existing 7.2 ceiling,
so evaluation stopped there and the unattempted OFF measurements remained missing.
The candidate was retained as rejected, with no rank. Two other prefix-screen
survivors were explicitly labeled unverified because the full-output budget was
one; neither received a rank. This run demonstrates the distinction between a
prefix-screen pass and a full-output result. It does not establish a working GFP
design or guarantee that checking additional finalists would yield one.

A control run without rotating the grid between pairs took 57.062 seconds and
admitted no candidate from the same 20-design budget. Most of that budget was
spent on the same natural closure across pairs and stems. This comparison tests
coverage under a limited budget; it does not establish an optimal pair count,
sampling policy or grid, or a guaranteed nonempty result for other inputs.

The earlier context probe reconstructed a specifically selected historical
positive from the pinned references. It took 1.926 seconds for the 161-nt switch
alone and 2.448 seconds with the 170-nt short-output transcript; both passed the
22 checks. The same switch with the entire 878-nt GFP transcript took 116.587
seconds and failed `A_M_11 > 0.5`. This selected example is not a general search
yield estimate. It demonstrates context dependence in that selected example; it does not establish
which context is more accurate. Mandatory full-CDS eligibility was subsequently
removed to restore the team's declared switch-through-linker model.

Historical reproduction at revision `679ea32` (not the current compiler):

```console
uv run --locked --extra dev python tools/pair_budget_on_pfas.py --pipeline --pipeline-output other --seed 7 --max-designs 20 --max-pairs 8 --full-finalists 2 --run-dir var/prokaryotic-and-compiler-rotated-custom --out var/prokaryotic-and-compiler-rotated-custom.json
```

Historical GFP reproduction at revision `679ea32`:

```console
uv run --locked --extra dev python tools/pair_budget_on_pfas.py --pipeline --pipeline-output gfp --seed 7 --max-designs 20 --max-pairs 8 --full-finalists 1 --run-dir var/prokaryotic-and-compiler-rotated-gfp --out var/prokaryotic-and-compiler-rotated-gfp.json
```

The same tool also exposes `--pilot` for the bounded pair-policy comparison and
`--regression-contexts` for the selected historical context probe. Raw regenerated
runs live under ignored `var/`. Small checked evidence archives preserve measured
results separately from those mutable run directories. Runtime is a local
measurement on Windows/Python 3.13 and varies by hardware, output sequence and
concurrent load; the budgets limit counted work, not elapsed wall-clock time.

The raw complete-run summaries had these SHA-256 digests:

- Pre-rotation custom control: `0e04d79d0b01d6fec44ec26243d3abc82a14f4f9b067b4172583615e15eb6f2f`.
- Rotated custom run: `ebce54c840eb595d3422e80f71c5a16682449bd600e12957ced02e36642573b7`.
- Rotated GFP run: `a5afc85e05e752ebea3f73e8a4644aa9f35d2fd0844f9270328983005a8c7f1c`.
