# V2 Algorithm Implementation · 2.0.1

This document describes the current code. See [API.md](API.md) for requests and responses, and [DATA_DICTIONARY.md](DATA_DICTIONARY.md) for frozen reference sources, model choices and table fields.

## 1. Complete pipeline

```text
Frozen references → verify hashes, coverage and normalization
Input → validate one CDS → translate with table 11 → lock first codon, stop and user positions
Shared constraints → score original input → immutable pool with fixed seeds
Selected strategies → independent states, SHA-256 subseeds, budgets and mutable regions
Candidates → optional repeat repair → final hard-constraint checks → select one per strategy
Merge identical DNA → calculate all available metrics → complete CDS output, optional comparison, FASTA / CSV / JSON
```

V2 runs the selected independent strategies without calling V1 or combining metrics into a weighted total score.

## 2. References and scoring masks

`config/defaults.json` locates each host directory. Loading verifies files against the manifest's SHA-256 hashes. CAI, tAI, whole-CDS preference and ranks are checked separately; unavailable components retain their own reasons.

| Metric | Reference | Scored target positions |
|---|---|---|
| Host sampling | Family probabilities in `host_codon_counts.csv` | Mutable sense codons; fixed positions copied |
| `host_preference` | Whole-CDS counts relative to the family maximum | Exclude first codon and stop; retain internal Met/Trp |
| CAI | Strain-specific `cai_weights.csv` | Exclude a recognized start, stop and Met/Trp |
| tAI | `tai_classic_weights.csv` or `stai_weights.csv` | Exclude fixed first codon and stop; retain internal Met/Trp |
| Harmonization | Midranks of whole-CDS frequencies within each family | Exclude first codon, stop and positions without synonymous alternatives |

Ribosomal reference construction excludes start and stop codons. Unobserved codons receive 0.5, but an entirely unobserved family causes an error. Both strains have CAI and both tAI model tables. A target with no scored positions returns `null + no_scored_codons`.

## 3. CAI and tAI

```text
p_host(c|a) = N_host(c) / Σ[d∈Syn(a)] N_host(d)
w_CAI(c)   = corrected_N_ribosomal(c) / max[d∈Syn(a)] corrected_N_ribosomal(d)
CAI        = exp(mean(log(w_CAI(c))))

W_tAI(c)   = Σ[decoding tRNAs j] (1-s(c,j)) × gene_copy_number(j)
w_tAI(c)   = W_tAI(c) / max[all 61 sense codons d] W_tAI(d)
tAI        = exp(mean(log(w_tAI(c))))
```

tAI normalizes across all sense codons rather than within synonymous families. The default uses classic penalty coefficients with bacterial decoding rules. Reference files record role inference, A34 modification assumptions, the Ile-CAT lysidine branch, gene copies and individual contributions. Runtime stAI reads frozen fitted weights; it does not refit them to the user's CDS.

Method references: [Sharp & Li](https://academic.oup.com/nar/article/15/3/1281/1166844) and [Sabi & Tuller](https://academic.oup.com/dnaresearch/article/21/5/511/2754544). Numerical agreement is not validation of expression prediction.

## 4. Joint RNA opening energy

The context is the fixed, actual transcribed upstream sequence plus a CDS prefix, 150 nt by default. The default target is CDS nt 1–15. Short CDS inputs use the available interval and report actual coordinates.

The frozen model specifies ViennaRNA 2.7.2, the Turner 2004 parameter SHA-256, 37°C, dangles=2, betaScale=1, salt=1.021 M and other options. Salt is a computational default, not a host measurement.

Use two independent fold compounds:

```text
G_all  = ensemble free energy without a structural constraint
G_open = ensemble free energy with the entire target forced unpaired
ΔG_open = G_open - G_all
log(P_open) = -ΔG_open / (0.0019872041 × (temperature_c + 273.15))
```

MFE is computed first for partition-function rescaling, followed by ensemble free energy. Target constraint characters are `x`; other positions use `.`. Opening energy is not a difference between two MFEs, and the joint opening probability is not a product of single-position probabilities. See [the ViennaRNA partition-function documentation](https://www.tbi.univie.ac.at/RNA/ViennaRNA/doc/html/partfunc/global.html).

Only negative rounding differences within 1e-5 kcal/mol may be clamped to zero, with a record. Larger negative differences, nonfinite values and version mismatches have explicit errors. `P_open` and opening energy express the same objective and are not scored twice.

Without upstream sequence, the context is labeled `cds_only`. Pairing arcs illustrate the MFE dot-bracket structure; opening energy still comes from the ensemble. Request-local cache keys include context, target, temperature, parameter hash and engine version. A lock protects model loading and calculations.

## 5. Shared constraints and repeats

- **Translation:** table 11; valid alternative starts translate as initial Met. The first codon, existing stop and locked positions remain fixed.
- **Motifs:** ATCC supports none / AGCAGY / literal ACGT; the server enforces AGCAGY for KPA. Expand AGCAGC and AGCAGT, add reverse complements and deduplicate. A nucleotide automaton detects both strands, overlaps, codon boundaries and terminal-stop junctions within the submitted CDS.
- **GC:** exclude terminal stop. Global GC defaults to the host P5–P95 hard interval. Local GC defaults to a 60 nt window with 3 nt steps, report only. Include the final window and use actual length for short sequences.
- **Repeats:** detect homopolymers, tandem repeats with a primitive unit and exact direct repeats with two nonoverlapping occurrences. Indexed seeds are extended against actual characters and contained hits are merged; detection does not rely only on hashes. Resource-limited scans are explicitly marked incomplete.

`warn` only reports repeats. `repair` attempts bounded synonymous repair. `strict` accepts only complete scans with no above-threshold hits. Repair runs for at most three rounds and proposes single/double-position changes in repeated regions. Improvement is assessed by scan completeness, remaining hit count and total repeated length. Repair must preserve the strategy's primary objective and mutable region.

## 6. Dynamic programming for additive objectives

CAI/tAI maximize the sum of log weights; harmonization maximizes negative rank error. Length and scored positions are fixed, so these objectives are equivalent to maximizing the geometric mean or minimizing the mean rank difference.

The state is `(processed position, coding_GC_count, motif_state)`. Each state retains at most **five internal paths**, independently of the single delivered output. Stable ordering uses objective score, fewer changes and then DNA lexicographic order.

Enumerate allowed synonymous codons, update motif state and GC, then prune paths whose remaining minimum/maximum GC cannot reach the interval. A fixed stop participates in motif matching but not coding GC or metrics.

Exceeding the frontier limit switches to `beam_approx` and removes the exact guarantee. Transition/time limits interrupt DP while retaining valid initial candidates. Final selection considers better terminal paths and the seed pool.

Exact guarantees cover only motif, global GC and fixed positions represented by the DP state. Local GC and strict repeats are complete-sequence filters; enabling them does not establish global optimality or infeasibility for the full problem.

## 7. Host sampling and RNA search

The shared initial pool is independent of the selected strategy set and includes the original input, whole-CDS samples and start-window samples. Bounded feasibility DP supplies seeds if needed. RNA rejects seeds that change positions outside its mutable window and, if necessary, searches for a starting point within its own limits.

Host sampling independently draws codons according to family probabilities and rejects constraint violations. The accepted distribution therefore differs from the unconstrained host distribution; it is described as host-frequency-guided sampling.

RNA search proposes synonymous changes at 1–3 mutable codons, applies inexpensive checks and then calculates opening energy. The pool retains 20 better sequences and up to four exploratory sequences. The default is at most 128 distinct evaluated contexts, also limited by proposal count and time. Reaching a budget returns available results without claiming global optimality.

## 8. Codon harmonization

An explicit source host is required. Use a built-in reference or JSON whole-CDS counts for all 61 sense codons; the source is not inferred from GC. Custom counts and their hash are retained, and an all-zero family is rejected.

```text
rank_host(c) = (number of strictly lower family counts + 0.5 × number of equal family counts) / family_size
error = mean(abs(rank_target(candidate_i) - rank_source(original_i)))
```

This is the project's position-wise `harmonize_rank_v1`, not a complete reproduction of CHARMING or ChimeraMap. The web interface's 10-position sliding mean is only a display aid, not the search objective.

## 9. Final selection and merging

Each strategy delivers one sequence. CAI, tAI, RNA and harmonization choose the best valid primary objective; ties favor fewer changes and then DNA lexicographic order. Host sampling chooses a valid representative in reproducible sampling order, without using another score to turn sampling into maximization. If the original input passes all hard constraints, non-sampling strategies first discard variants with a worse primary objective.

Output count is separate from search width. DP explores up to five paths per state. The internal repair shortlist contains up to 15 candidates and uses objective value and codon distance to retain differences. Repair and hard-constraint filtering precede the final single output. RNA pools and other budgets remain multi-candidate searches.

```text
codon_distance = differing codons at mutable positions / number of mutable positions
```

Identical DNA is stored once with each strategy's objective value, source-seed hash and repair record. The web interface shows a complete CDS and preference label first, with direct copying and single-sequence FASTA download; metrics start collapsed. The first selected preference is shown initially. If unavailable, an explicit message identifies the fallback to another completed result. Preference cards switch outputs; a manual choice is not replaced when another strategy finishes. Display order does not affect scoring.

Expanded analysis has one row per preference; identical DNA refers to the same ID. There are no within-strategy alternatives or candidate expansion controls. The original input is a baseline. **Details** does not change the main output; **Use this sequence** does. Collapsing analysis preserves the output and batch selections, and comparison/export deduplicate DNA. Output, inspection and comparison selections are separate states, all cleared when a new run starts.

Final candidates are translated, constraint-checked and scored for every available metric. Missing values use `null + reason`. Run records contain code/reference hashes, contexts, seeds, the initial pool, budgets and stopping reasons.

## 10. Validation

Checks cover hand-calculated metrics, Biopython cross-checks, exhaustive small-space DP, joint RNA probabilities and coordinates, overlapping motifs, GC endpoints, repeat repair, hard constraints, strategy independence, failure isolation and deduplication. Real browser checks cover all five preferences, complete-sequence output, exact clipboard contents, single/batch FASTA, independent inspection, empty results, explicit fallbacks, selection retention, comparisons, structures, English text and mobile layouts.

See [VALIDATION.md](VALIDATION.md) for observed results. These are computational checks, not expression experiments.
