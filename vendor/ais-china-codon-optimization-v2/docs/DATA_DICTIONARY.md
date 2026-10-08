# Reference Data and Field Dictionary

Strain-specific tables are in `data/hosts/<host_id>/2026-09-06.v1/`. CSV files use UTF-8 with a BOM and DNA letters A/C/G/T. JSON GC values are fractions from 0 to 1; displayed percentages multiply these values by 100.

Reference package: `2026-09-06.v1`.

## Sources and model choices

### Hosts, sources and QC

| Item | ATCC 6919 | KPA171202 |
|---|---|---|
| Assembly | GCF_008728435.1 | GCF_000008345.1 |
| Chromosome | NZ_CP044255.1 | NC_006085.1 |
| V1 package annotation release | 2026-03-22 | 2025-04-02 |
| V2 GenBank record date | 2026-03-26 | 2026-04-12 |
| GenBank CDS features | 2,384 | 2,424 |
| V2 QC-passing records | 2,312 | 2,345 |
| Excluded CDS records | 72 | 79 |

NCBI references: [ATCC 6919](https://www.ncbi.nlm.nih.gov/nuccore/NZ_CP044255.1) and [KPA171202](https://www.ncbi.nlm.nih.gov/nuccore/NC_006085.1). The ATCC ZIP includes GenBank; the KPA ZIP has sequence and related files but lacks full GenBank annotation, which was retrieved for the same accession using NCBI EFetch.

QC requires a complete table 11 CDS, valid start and terminal stop, no internal stop, no pseudogene or special translation exception, and agreement between the translated extraction and annotated protein. Biopython handles both strands and compound locations.

ATCC V2 codon counts exactly match V1. KPA has 37 locus-difference rows: nine records newly pass QC, three no longer pass, and 20 shared QC-passing records have sequence changes. V1 counts remain frozen. See [KPA annotation_changes_vs_v1.csv](../data/hosts/kpa171202_GCF_000008345.1/2026-09-06.v1/annotation_changes_vs_v1.csv).

### CAI reference choice

Each strain has **61 structural ribosomal protein reference genes**. After excluding the first start codon and terminal stop, the reference contains **8,029 codons for ATCC** and **8,021 for KPA**.

Selection excludes modifying enzymes whose names contain “ribosomal protein”, including RimO and RimI. Inclusion/exclusion evidence is in `cai_reference_selection.csv`. This is a ribosomal protein proxy reference, not a measured high-expression set.

Weights use `w(c)=N(c)/max_synonymous N`, replacing zero counts with 0.5 only when other family members are observed. Sequence scoring excludes start, stop and internal Met/Trp and uses the geometric mean. Weights and sequence CAI were independently cross-checked with Biopython under matching conventions. Definition: [Sharp & Li](https://academic.oup.com/nar/article/15/3/1281/1166844).

The [CodonStatisticsDB KPA ribosomal counts](http://codonstatsdb.unr.edu/data/1747/ribosomal_codon_statistics.tsv) were also downloaded and kept separately: 2021, 60 genes and 9,085 total codons. Their annotation year, gene set and start-counting convention differ from this package. A comparison table was generated, but these counts were not mixed into default CAI. The database's precomputed per-gene CAI reference is also distinct; see [the database paper](https://academic.oup.com/mbe/article/39/8/msac157/6647594).

### tRNA decoding and stAI diagnostics

Each strain has **45 tRNA loci with annotated anticodons and 44 amino-acid/anticodon groups**. Independent GenBank extraction agrees with the earlier tRNA snapshot.

Met-CAT and Ile-CAT are handled separately. Initiator/elongator Met roles are inferred from the three G–C pairs in the anticodon stem; actual sequences and evidence fields are retained. See [the initiator tRNA feature study](https://pmc.ncbi.nlm.nih.gov/articles/PMC5389676/). This remains an inference, not an experimentally confirmed classification for these strains.

| Strain | Inferred initiator Met tRNA, excluded from elongation supply | Inferred elongator Met tRNA |
|---|---|---|
| ATCC 6919 | F6X01_RS06835 | F6X01_RS10070 |
| KPA171202 | PPA_RS06450 | PPA_RS09535 |

Ile-CAT decodes ATA through the bacterial lysidine route; both strains have TilS annotations. A34-to-I and other wobble relationships are recorded as assumptions in `tai_model.json`. Individual tRNA-to-codon contributions are in `tai_decoding_edges.csv`.

Classic penalties are WC=0, G–U=0.41, I–C=0.28, I–A=0.9999, U–G=0.68 and L–A=0.89. Compute `W=Σ(1−s)×tGCN`, then divide by the maximum W across all 61 sense codons. Both strains have 61 positive weights with **no zero-weight imputation**. These classic coefficients were not measured in C. acnes; see [Sabi & Tuller](https://academic.oup.com/dnaresearch/article/21/5/511/2754544).

The two strains have identical grouped tRNA copy configurations under this model, so their classic weight tables are identical, as verified by file hashes. Strain-specific provenance and loci remain separate. Equal model weights do not imply equal expression behavior.

A bounded search with 35 starting points maximizes Spearman(tAI, DCBS), producing the separate `stai_dcbs_hillclimb_v1` model. Fitting uses CDS records with at least 100 elongation codons. Protein-sequence hashes split training and held-out groups so identical proteins cannot cross the split. Close homologs can still occur in both groups; the split supports model diagnostics only.

| Held-out DCBS correlation | ATCC 6919 | KPA171202 |
|---|---:|---:|
| Held-out genes | 381 | 381 |
| Classic tAI | 0.1778 | 0.1747 |
| Fitted stAI | 0.1499 | 0.1843 |

ATCC's held-out correlation did not improve; KPA's improvement was small, and some fitted parameters approach their bounds. The classic model therefore remains the default; stAI is an exploratory alternative. **These correlations diagnose agreement with DCBS, not expression accuracy.** Search details, differences from the original method, all starts and coefficients are saved. The implementation is not presented as an exact reproduction of stAIcalc.

### GC and static parameters

| Metric | ATCC 6919 | KPA171202 |
|---|---:|---:|
| Length-weighted coding GC | 60.3979% | 60.4047% |
| Per-CDS coding GC P5 | 54.4885% | 54.6915% |
| Per-CDS coding GC P95 | 64.9867% | 64.9859% |

Coding GC includes the first codon and excludes terminal stop. P5–P95 uses equally weighted CDS records and linearly interpolated quantiles, not quantiles of a concatenated genome-wide sequence. Local GC uses 60 nt windows with 3 nt steps and includes the final full window; short sequences are recorded separately.

The build also generated genetic code table 11, a two-strand/overlap AGCAGY automaton, repeat-screening defaults and 3,721 sense-codon-pair counts per strain. Pair counts support future method development; they are neither ChimeraMap nor a validated codon-pair optimization objective.

### RNA model and backgrounds

ViennaRNA 2.7.2 was installed and its [Turner 2004 energy parameters](../config/rna_turner2004.par) exported. Temperature, salt, dangles, constraint type and engine version are in [rna_model.json](../config/rna_model.json). Salt uses the software default, not measured intracellular C. acnes conditions.

For all 4,657 QC-passing CDS records, the build calculated the ensemble free-energy difference required to keep nt 1–15 simultaneously open within the first 150 nt: `ΔG_open=G_open−G_all`, with `P_open=exp(−ΔG_open/RT)`. It uses two partition-function calculations, not MFE differences. See [the ViennaRNA partition-function documentation](https://www.tbi.univie.ac.at/RNA/ViennaRNA/doc/html/partfunc/global.html).

Median CDS-only opening energies are **4.6214 kcal/mol for ATCC** and **4.6440 kcal/mol for KPA**. These backgrounds omit actual 5′UTRs, do not assess expression across a complete initiation region, and are not default hard thresholds. User constructs require their actual transcribed upstream sequence and a new fold calculation.

## Master table: codon_parameters.csv

Each strain has 61 rows, covering sense codons only.

| Field | Meaning and calculation |
|---|---|
| `codon_dna` / `codon_rna` | DNA / RNA representation of the same codon |
| `amino_acid` | One-letter amino acid for an internal position under table 11 |
| `synonymous_family_size` | Number of synonymous codons for the amino acid |
| `gc_bases` | Number of G/C bases in the codon, from 0 to 3 |
| `v1_count` | Raw count in the frozen V1 reference; includes valid first codons and excludes stops |
| `v2_qc_count` | Count recalculated from this package's GenBank/QC set; also includes starts and excludes stops |
| `sampling_probability_v1` | `v1_count / sum of family counts`; sums to 1 within each family |
| `host_preference_v1` | `v1_count / maximum family count` |
| `harmonization_midrank_v1` | Number of family members with lower counts plus half the number with equal counts, divided by family size |
| `cai_reference_count` | Count in the strain's structural ribosomal protein reference, excluding reference starts/stops |
| `cai_weight` | Count after zero-count handling, divided by the family's maximum reference count |
| `tai_classic_W` / `tai_classic_w` | Absolute supply and all-sense-codon normalized weight under classic penalties |
| `stai_W` / `stai_w` | Absolute supply and normalized weight under the exploratory DCBS-fitted model |

CAI and tAI weights use different normalization scopes and are not interchangeable. Sequence CAI excludes the first position, stop and internal Met/Trp; project tAI excludes the first position and stop but retains internal Met/Trp. Both use the geometric mean of eligible position weights.

## References and QC

| File | Contents |
|---|---|
| `manifest.json` | Host, assembly, source hashes, annotation date, rules, builder code hashes and output hashes |
| `cds_qc.csv` | Locus, protein ID, location, length, pass/fail and exclusion reason for each CDS feature |
| `reference_cds.fasta` / `reference_proteins.fasta` | QC-passing CDS records and individually checked proteins, identified by locus tag |
| `cai_reference_selection.csv` | All candidates matching “ribosomal protein” and inclusion/exclusion evidence |
| `cai_reference_genes.csv` / `cai_reference_cds.fasta` | Structural ribosomal protein reference actually used for CAI |
| `cai_weights.csv` | Raw reference counts, zero-count handling and final CAI weights |
| `host_codon_counts.csv` | V1/V2 counts, differences, sampling probabilities, host preference, RSCU and harmonization ranks |
| `annotation_changes_vs_v1.csv` / `annotation_comparison.json` | Differences between reference sets, sequences, QC status and annotation versions |

QC `location` uses Biopython's 0-based, end-exclusive representation; `(-)` denotes the reverse strand. Do not interpret it directly as the interface's 1-based coordinates. FASTA sequences are oriented in the transcribed direction.

KPA also includes `cai_published_kpa_comparison.csv` and `cai_published_kpa_metadata.json`, retaining the original conventions of a published 2021 ribosomal reference. This is not the default reference and must not be applied to ATCC.

## tRNA and tAI

| File or field | Meaning |
|---|---|
| `trna_genes.csv` | One row per independent tRNA locus, including transcribed sequence, anticodon and role evidence |
| `anticodon_offset_0based` | Anticodon start in the tRNA's 5′→3′ sequence |
| `role` | `elongator`, `initiator_inferred` or `elongator_inferred`; the latter two distinguish Met roles |
| `role_evidence` | Source of role assignment, including sequence-based inference and canonical anticodon-loop alignment assumptions |
| `trna_copy_counts.csv` | Joint amino-acid/anticodon groups, separating raw copies from elongation-model copies |
| `tai_decoding_edges.csv` | Contribution of one tRNA to one codon, retaining pairing class and assumptions |
| `tai_classic_weights.csv` | 61 positive weights using published classic s values |
| `tai_model.json` | Model definition, s values, TilS annotation, Met roles and all assumptions |
| `stai_weights.csv` / `stai_s_values.csv` | Separately fitted weights and s values; classic values remain intact |
| `stai_fit_multistart.csv` | Results, evaluation counts and stopping reasons for 35 starting points |
| `stai_fit_diagnostics.json` | Fit conventions, groups, seeds, objective correlations and limitations |

Pairing classes use RNA letters: `WC` denotes direct effective pairing in the model; `G_U` means anticodon G with codon U; `I_C` and `I_A` follow the inosine route; `U_G` means anticodon U with codon G; and `L_A` follows the lysidine route. DNA T in genomic CSV files corresponds to RNA U.

`W(c)=Σ(1−s)×tGCN`; `w(c)=W(c)/max_all_sense(W)`. An absent directly complementary anticodon does not imply an absence of decoding tRNAs; the declared wobble rules must be considered. `imputed=False` means no artificial small value was used to fill a missing codon weight.

## Per-gene metrics and backgrounds

`native_gene_metrics.csv` combines locus, length, GC, local GC, CAI, classic tAI, DCBS, stAI, fitting group, CDS/protein hashes and CDS-only RNA metrics.

- `sense_codons` includes the first codon; `elongation_codons` excludes it. Both exclude stop.
- `coding_gc_fraction` excludes stop; `sequence_gc_fraction` includes it.
- `gc3_fraction` counts only the third base of each codon in the sense region.
- `dcbs_elongation` estimates nucleotide backgrounds separately for the three codon positions in each sequence, takes the larger of the observed/expected ratio and its reciprocal, and calculates an arithmetic mean across positions. No pseudocount is added.
- `stai_fit_group` is `training`, `heldout_diagnostic` or `excluded_short`. Genes with fewer than 100 elongation codons can still be scored but are excluded from fitting.
- `ribosomal_reference=True` identifies genes used to construct CAI weights. Their CAI statistics include the influence of the reference itself.

`coding_gc_distribution.json` stores per-gene quantiles and length-weighted aggregate GC. The 61 rows of `local_gc_60nt_histogram.csv` represent 0–60 G/C bases in a 60 nt window; they are not codon rows. Short windows are in `local_gc_short_windows.csv`.

`codon_pair_counts.csv` contains 61×61=3,721 rows of adjacent elongation-codon counts within CDS records, never across genes. The denominator of `conditional_pair_frequency` is the count of the corresponding amino-acid pair; it is empty when that pair is absent. No pseudocount or optimization score is derived from these counts.

## RNA

`config/rna_model.json` and `config/rna_turner2004.par` freeze the model. `native_rna_cds_only_background.csv` reports the following for each gene:

| Field | Meaning |
|---|---|
| `context_mode` | Fixed as `cds_only` in this package; no actual 5′UTR included |
| `context_length_nt` / `context_dna` | Actual prefix length and sequence, up to 150 nt |
| `target_start_nt_1based` / `target_end_nt_1based` | Inclusive target positions in the context |
| `ensemble_free_energy_all_kcal_mol` | Ensemble free energy without a target pairing constraint |
| `ensemble_free_energy_open_kcal_mol` | Ensemble free energy with the entire target forced unpaired |
| `delta_g_open_kcal_mol` | Constrained minus unconstrained energy; lower means easier simultaneous opening in the model |
| `log_p_open` / `p_open` | Joint probability that the entire target is unpaired, not a product of individual probabilities |
| `mfe_kcal_mol` / `mfe_structure` | Minimum-free-energy structure of the same context, for supporting display |
| `roundoff_clamped` | Whether a tiny negative difference was corrected to zero within the recorded tolerance |

`rna_background_distribution.json` summarizes these CDS-only values descriptively; it does not define expression thresholds.

## Global configuration and integrity

`config/defaults.json` separates data-derived GC intervals, model choices and engineering screening thresholds. `config/genetic_code_11.csv` has 64 rows. `config/motif_AGCAGY_automaton.json` contains the four expanded, two-strand motifs and nucleotide state transitions.

`reports/parameter_file_inventory.csv` records paths, byte sizes, CSV row counts and SHA-256 hashes. `requirements-lock.txt` pins the Python dependencies used for the build. If reference files change, rerun the full build or final aggregation; stale hashes cannot identify a newly verified version.

## Rebuilding and checking the package

Run `python scripts/run_all.py --offline` from the project root with the full pinned dependencies. Keep `data/raw/` to reproduce the build. The original parameter checks and six-table hash comparison are retained in [the reproducibility record](../reports/reproducibility_check.json); see [Validation](VALIDATION.md) for the full test scope and commands.
