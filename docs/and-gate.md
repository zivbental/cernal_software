# The eukaryotic two-input AND gate

`eukaryotic_toehold_and` designs a **two-hairpin toehold construct** that is meant to make its
payload only when **two** chosen RNAs are both present. It is the first gate with two inputs that
can be chosen in the application, run by the worker, saved with the run, reopened and exported.
It is a computational design: **no AND construct has been experimentally validated.**

Science and definitions: [`notebooks/toehold_and/eu_and_v3_spec.md`](../src/engine/gates/notebooks/toehold_and/eu_and_v3_spec.md).
The code that measures it is one shared module,
[`engine/gates/tools/stem_opening.py`](../src/engine/gates/tools/stem_opening.py), used by this gate
and by the `eu_and_v3` notebook, so the two cannot report different numbers.

## What is supported

| | |
|---|---|
| Hosts | `human`, `yeast` (a bacterial host is refused: `not production supported for ecoli`) |
| Inputs | a **differential-expression table** and two genes picked from it (the same gene twice is allowed: two windows of one transcript). A pasted sequence or a single reference gene cannot name two inputs and is refused |
| Genes | both must pass gene selection and be **up-regulated**; a down-regulated or filtered gene fails the run naming the gene and the stage-1 reason |
| Outputs | the same as any Human or yeast run (GFP, mCherry, luciferase, custom coding sequence) |
| One run | one AND gate; it is not combined with single-input families in the same run |

`GET /api/version` states this, and the wizard and the API both read it:
`family_hosts`, `family_inputs` (`eukaryotic_toehold_and: 2`), `family_input_modes` (`["de"]`) and
`limits.max_gate_inputs` (2). The single-input default is unchanged (`limits.max_triggers` is 1), and
naming no family never selects the AND gate.

## Using it in the application

1. **Step 1 · Inputs.** Choose **Human** or **Yeast**, then a differential-expression dataset
   (public or uploaded).
2. **Step 2 · Logic.** Choose **Eukaryotic AND Toehold** (marked *2 inputs*). The input modes that
   cannot name two genes are disabled, and two selectors appear, listing the dataset's
   up-regulated genes: **Input A** (5′ hairpin) and **Input B** (3′ hairpin).
3. Choose a payload and vector as usual, then **Compile & Optimize**.
4. Open the run. Each candidate shows its score decomposition and an **AND evidence** panel: ON,
   OFF, ON − OFF, ΔG, whether it is tied with the best, every folded state with its sampler check,
   and the controls. Unmeasured values read *unmeasured*; a failed sampler check reads **FAILED**
   and is repeated as a warning.
5. Download the summary table (extra `and_*` columns), the report, and, only once sequence release
   is approved, the FASTA, GenBank and SBOL files.

The gate and its two genes are chosen in step 2 (screenshot of the running application):

![Step 2 of the wizard with the Eukaryotic AND Toehold selected and its two input genes](assets/and-gate-wizard.png)

and each candidate's page shows what its ON and OFF came from:

![The AND evidence panel of the top candidate: ON, OFF, each folded state and its sampler check](assets/and-gate-results.png)

## The same run through the API

```http
POST /api/runs
{
  "input_mode": "de",
  "dataset_id": "<id of an uploaded DE table with SELE and ICAM1>",
  "organism": "human",
  "gate_families": ["eukaryotic_toehold_and"],
  "seed": 7,
  "params": {
    "constraints": {"max_triggers": 2, "max_circuit_gates": 1},
    "and_inputs": {"gene_a": "SELE", "gene_b": "ICAM1"},
    "payload": {"outputs": ["gfp"]},
    "budget": {"max_designs": 8}
  }
}
```

`max_triggers` must say 2 (one gate with two inputs), `max_circuit_gates` stays 1, and `and_inputs`
is required. `params.and_gate` is optional and accepts the settings below; unknown names and
out-of-range values are a `422` naming the field. `POST /api/design` accepts the same
`and_inputs` and `and_gate` fields.

### One real run

Human, the table `ENSG00000007908 SELE log2FC 3.4` and `ENSG00000090339 ICAM1 log2FC 2.6`, default
settings, seed 7, ViennaRNA. It finishes in about **50 s** on a laptop: 8 candidates, all accepted,
a tied group of 2, and **32 of 32** sampler checks verified.

| rank | spacer | ON % | OFF % | OFF set by | ON − OFF | tied | ΔG kcal/mol | score |
|---:|---|---:|---:|---|---:|:-:|---:|---:|
| 1 | none | 100.00 | 0.89 | +B | 99.11 | yes | −17.3 | 0.624 |
| 2 | none | 100.00 | 0.89 | +B | 99.11 | yes | −17.5 | 0.624 |
| 3 | none | 100.00 | 1.26 | +A | 98.74 | no | −19.0 | 0.620 |
| 4 | none | 100.00 | 1.32 | +A | 98.68 | no | −19.0 | 0.618 |
| 5 | spacer | 100.00 | 1.32 | +B | 98.68 | no | −17.6 | 0.615 |
| 6 | spacer | 100.00 | 1.48 | +B | 98.52 | no | −18.5 | 0.609 |
| 7 | spacer | 99.87 | 1.67 | control | 98.20 | no | −14.3 | 0.593 |
| 8 | spacer | 99.97 | 1.86 | control | 98.11 | no | −14.5 | 0.587 |

The seed-to-seed noise of ON − OFF was 0.09 points (median) and 0.14 (95th percentile), so the two
best candidates are the tied group and the rest are not clearly worse than each other. **What the
numbers do not say:** they are structural predictions at 37 °C and 0.1 M salt, not measured
expression. The leak that sets OFF is almost always one trigger partly opening the *other*
hairpin (`+A`, `+B`), not the bare construct.

## What is computed

1. **Genes and windows.** Stage 1 runs on the two chosen genes only. Stage 2 scans their
   transcripts; for this gate a window containing `AUG` or `CAU` is skipped (the hairpin is built
   from the window and from its reverse complement, so either puts a second start codon into the
   switch), and `windows_per_gene` distinct, non-overlapping windows are kept per gene.
2. **Single switches.** The inherited toehold sweep builds each trigger's hairpins in the
   *trailing-Kozak* layout (prefix, toehold, stem↑, loop, stem↓, Kozak, AUG). The
   `singles_per_trigger` best of each trigger, by sampled `ON − OFF` of the single switch, go on.
3. **Fusing.** For both orders (A at the 5′ end, then B), each pair of single switches and each
   spacer variant, the first hairpin is cut at its own Kozak and the second hairpin joined after its
   prefix. Every relocated domain is checked to hold its original sequence. The designs are sorted
   by the screen scores of their halves, so `budget.max_designs` keeps the most promising.
4. **Validation.** The shared `SwitchValidator`: exactly one start codon (the payload's), no
   in-frame stop, no forbidden motif, a target structure that folds. A rejected design keeps its
   reason in the run summary.
5. **Evaluation.** For the fused switch plus the first 30 nt of the payload after the start codon,
   the four states (alone, +A, +B, +A+B) and `n_controls` mismatched-trigger controls are folded;
   `n_samples` structures are drawn from each sampled state, and
   `Open = E[min(rA/LA, rB/LB)]` is the joint opening of the two stems, each relative to its own
   length. **ON** is the +A+B state; **OFF** is the largest of alone, +A, +B and the controls. A
   second sampling with another seed gives the noise that defines the tied group.
6. **Checks.** Each sampled state is compared with the exact base-pair probabilities; a failed
   check is kept, shown and counted, never corrected.

Scored metrics are the profile's own names, raw: `predicted_leakage = OFF/100` (a structural proxy,
not a measured leak), `dynamic_range = ON / max(OFF, 1%)`, `state_separation` its log2,
`gate_folding_energy` the MFE, `trigger_accessibility` the lower of the two triggers',
`gc_content`, `predicted_success_rate`, and `circuit_complexity` 3. `orthogonality` is not emitted.

## Settings (`params.and_gate`)

| Field | Default | Meaning |
|---|---:|---|
| `n_samples` | 2000 | structures drawn per sampled state |
| `screen_samples` | 300 | draws used to rank single switches before fusing (ordering only) |
| `n_controls` | 5 | mismatched-trigger controls per candidate |
| `controls_sampled` | false | `false`: each control's exact-matrix upper bound; `true`: sample it (ViennaRNA's sampler can disagree with its matrix on mismatched states, so the bound is the default) |
| `windows_per_gene` | 3 | distinct trigger windows kept per input gene |
| `singles_per_trigger` | 3 | single-switch variants of each trigger that are fused |
| `spacer_variants` | both | `no_spacer`, `spacer` |
| `spacer_min_length`, `spacer_max_length`, `spacer_pool_size` | 15, 20, 150 | the seeded spacer pool |
| `max_overlap_nt`, `wobble_max_fraction` | 8, 0.5 | longest identical or complementary run allowed between the two triggers and a control and a trigger |
| `verify_sigma`, `verify_floor_nt` | 4.0, 0.02 | sampler-check tolerance `σ·sd/√N + floor` |
| `off_floor_pct` | 1.0 | OFF below this is replaced by it in `dynamic_range` only |
| `noise_check`, `noise_seed_offset` | true, 1000 | second sampling that defines the tied group |

The folding model defaults to **0.1 M monovalent salt** for an AND run (the ViennaRNA library
default, 1.021 M, is a standard state, not a cell); set `params.folding.salt_molar` to override. The
effective value is recorded in the run's configuration and its folding-model provenance.

## What is saved

Everything is saved with the run and survives reopening: the gate family and its version, the
frozen configuration (both genes, the settings, the folding model), each candidate's two triggers,
metrics, `design.and_gate` (state-by-state Open, sampler checks, controls, ΔG, tie, noise),
warnings and rejection reasons, and the run's `scientific_provenance.and_gate` (settings, noise
band, tied group, sampler-check totals). Rejected candidates are kept with their reason and no
rank. The sequence-release checks are unchanged: with no screening adapter configured the
sequences, the manifest and the sequence exports are withheld, while `design.and_gate` (numbers
only) is disclosed through an explicit whitelist.

## Limits and open questions

- **No experimental validation**, and no sensitivity analysis of the declared defaults (8 nt
  overlap, 5 controls, 0.1 M salt) has been run.
- **Different switches than the notebook.** The single switches come from the engine's own
  generator (same prefix, 18 nt stem and `GCCACC` Kozak as the NucSyn designs `eu_and_v3` fuses),
  not a NucSyn table, so numbers are not expected to match a notebook run on the same genes.
- **Ranking.** `engine.scoring` ranks the candidates (weighted score over the profile's metrics),
  not `ON − OFF` alone; the tied group is reported beside the ranking, not used to reorder it.
- **`gate_folding_energy` saturates.** Two stable hairpins have an MFE near −80 kcal/mol, below the
  profile's −60 floor, so the normalised score is its best for every AND candidate and does not
  discriminate between them. The raw value is reported unchanged; a per-gate range is a profile
  decision.
- **Controls** are windows of other transcripts of the host's reference (seeded), not the notebook's
  triggers of other designs.
- **Payload.** Only the first 30 nt after the start codon are folded, as in the notebook; whether
  the rest of the payload changes the ranking is untested.
- **Compute.** About 2–3 s a candidate at the defaults; `budget.max_designs` bounds the number
  evaluated (default 20).

## Tests

- `tests/api/test_and_gate_run.py`: the flow above through the real stack (capabilities,
  submission, worker, saved results, reopening, exports, the release gate, rejections, bad inputs,
  every unsupported combination, and a single-input run still working).
- `tests/engine/gates/test_eukaryotic_and_gate.py`: the family, its settings and the shared tool.
- `frontend/e2e/and-gate.mjs` (`npm run test:and`): the evidence panel.
- The notebook's own tests still pass on the shared tool.
