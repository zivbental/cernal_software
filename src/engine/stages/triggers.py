"""Stage 2 — gate-aware trigger selection in transcript context.

Exact 30/33/36-nt windows map to the CERNAL 12/15/18-nt toehold variants.  RNAplfold
joint opening probabilities are mechanistic hypotheses, not biological-success
probabilities.  Mean marginal openness is retained as diagnostic evidence.
"""

import json
import math
import random
from collections.abc import Callable, Iterator

from engine import sequences as sq
from engine.domain import (
    Constraints,
    ProkaryoticAndSettings,
    SeedOpeningTrial,
    SelectedGene,
    TriggerCandidate,
    TriggerSet,
)
from engine.errors import JobCancelled
from engine.gates.tools.folding import FoldEngine
from engine.stages.folding import FoldProfiler
from engine.stages.motifs import MotifScreener


class TriggerScorer:
    """Scan transcripts and deterministically shortlist candidates per gate footprint.

    Exact gate-aware candidates are ranked independently within each footprint bucket by
    selected joint P8 (higher), terminal-20 opening free energy per nucleotide (lower),
    and terminal-20 mean marginal openness (higher). The per-gene budget is then filled
    round-robin across configured footprint buckets, preventing one footprint from being
    removed merely because another has more seed placements.

    Profilers without the joint-probability API retain the historical mean-marginal
    ranking. This compatibility path supports manually supplied/legacy profiler adapters;
    errors raised by an adapter that does provide joint probabilities are never caught.
    """

    TOP_K_PER_GENE = 50
    SELECTION_METHOD = "rnaplfold_gate_aware_joint_opening_v2"
    LEGACY_SELECTION_METHOD = "rnaplfold_mean_base_unpaired_v1"
    #: Footprint -> the length of the window's FREE toehold, the part not paired into a
    #: stem. The one-input entries are ``footprint - ARM_LEN`` (36 - 18 = 18). The 50-nt
    #: entry is trigger B of a two-input AND gate, whose paired part is the secondary
    #: invasion domain rather than the main arm: ``50 - SECONDARY_INVASION_LEN(18) = 32``,
    #: which is ``ToeholdAndGate.TOEHOLD_B_LEN`` exactly -- the free ``r2`` domain that
    #: nucleates against the switch's ``r2*``. The mapping's rule is unchanged; only the
    #: domain that does the pairing differs between the two chemistries.
    FOOTPRINT_TO_TOEHOLD = {30: 12, 33: 15, 36: 18, 50: 32}
    ALLOWED_SCANNED_LENGTHS = frozenset(FOOTPRINT_TO_TOEHOLD)
    HYPOTHESIS_LENGTH = 20
    SEED_LENGTH = 8
    GAS_CONSTANT_KCAL_PER_MOL_K = 0.00198720425864083
    TEMPERATURE_K = 310.15  # Legacy default; runtime uses the profiler's effective model.
    PU_FLOOR = 1e-12

    def __init__(
        self,
        profiler: FoldProfiler,
        screener: MotifScreener,
        folder: FoldEngine,
    ) -> None:
        self.profiler = profiler
        self.screener = screener
        self.folder = folder

    def compatible_pairs(
        self,
        genes: list[SelectedGene],
        sequences: dict[str, str],
        families: list,
        settings: ProkaryoticAndSettings,
        constraints: Constraints,
        *,
        seed: int,
        on_progress: Callable[[int, int], bool] | None = None,
    ) -> tuple[list[tuple[str, TriggerSet]], dict]:
        """Find the architecture's overlap before shortlisting whole pairs.

        Pair ordering uses the lower of the two window MEAN marginal unpaired
        probabilities. Candidate ``accessibility`` separately retains the MINIMUM
        marginal probability, as it does for single-input scanning. Neither is an
        experimentally calibrated probability of AND function. No independent top-K
        window filter is applied: that can erase the overlap this chemistry needs.
        """
        by_id = {gene.gene_id: gene for gene in genes}
        ids = list(by_id)
        profiles = {gene: self.profiler.profile(sequences[gene]) for gene in ids}
        rows = []
        discovered = 0
        screened = 0
        discovery_truncated = False
        seed_matches = 0
        discovery_scopes = {}
        # The chosen gene pair is a single search; roles are emitted by the family.
        first, second = ids[0], ids[-1]
        for family in families:
            remaining = settings.max_pair_seed_matches - seed_matches
            if remaining <= 0:
                discovery_truncated = True
                break
            finder_options = {"max_matches": remaining, "on_progress": on_progress}
            source = (
                family.find_trigger_pairs(sequences[first], **finder_options)
                if first == second
                else family.find_cross_gene_pairs(
                    first, sequences[first], second, sequences[second], **finder_options
                )
            )
            for pair in source:
                if discovered >= settings.max_pair_candidates:
                    discovery_truncated = True
                    break
                discovered += 1
                if discovered % 128 == 1 and on_progress is not None:
                    if not on_progress(discovered, settings.max_pair_candidates):
                        raise JobCancelled("Finding compatible trigger pairs")
                if not constraints.overlap_range[0] <= pair.len_x <= constraints.overlap_range[1]:
                    screened += 1
                    continue
                gene_a = getattr(pair, "gene_a", first)
                gene_b = getattr(pair, "gene_b", second)
                a0, a1 = pair.window_a()
                b0, b1 = pair.window_b()
                windows = (sequences[gene_a][a0:a1], sequences[gene_b][b0:b1])
                if any(self.screener.violations(window) for window in windows):
                    screened += 1
                    continue
                a_profile, b_profile = profiles[gene_a][a0:a1], profiles[gene_b][b0:b1]
                a_mean, b_mean = sum(a_profile) / len(a_profile), sum(b_profile) / len(b_profile)
                rows.append(
                    (min(a_mean, b_mean), family.geometry_name, gene_a, a0, a1, gene_b, b0, b1)
                )
            scope = dict(family.last_pair_search)
            discovery_scopes[family.geometry_name] = scope
            seed_matches += scope["seed_matches_considered"]
            discovery_truncated |= scope["discovery_truncated"]
            if discovery_truncated:
                break
        rows.sort(key=lambda row: (-row[0], *row[1:]))
        eligible = rows
        if settings.pair_selection == "percentile_sample" and rows:
            # Nearest-rank percentile: an explicit relative sampling rule, not a
            # new biological gate. Sampling without replacement uses the job seed.
            ascending = sorted(row[0] for row in rows)
            index = min(
                len(rows) - 1,
                max(0, math.ceil(settings.accessibility_percentile / 100 * len(rows)) - 1),
            )
            cutoff = ascending[index]
            eligible = [row for row in rows if row[0] >= cutoff]
            taken = random.Random(seed).sample(eligible, min(settings.max_pairs, len(eligible)))
            taken.sort(key=lambda row: (-row[0], *row[1:]))
        else:
            cutoff = None
            taken = eligible[: settings.max_pairs]

        cache: dict[tuple[str, int, int], TriggerCandidate] = {}

        def candidate(gene_id: str, start: int, end: int) -> TriggerCandidate:
            key = gene_id, start, end
            if key not in cache:
                gene = by_id[gene_id]
                sequence = sequences[gene_id][start:end]
                values = profiles[gene_id][start:end]
                cache[key] = TriggerCandidate(
                    trigger_id=f"pair-{gene_id}-{start}-{end}",
                    gene_id=gene_id,
                    symbol=gene.symbol,
                    sequence=sequence,
                    start_index=start,
                    openness=sum(values) / len(values),
                    accessibility=min(values),
                    mfe=self.folder.mfe(sequence).energy,
                    gc_content=sq.gc_content(sequence),
                    log2_fold_change=gene.log2_fold_change,
                    aug_indexes=sq.find_augs(sequence),
                    stop_indexes=sq.find_stops(sequence),
                    score=sum(values) / len(values),
                    rnaplfold_version=self.profiler.provenance(sequences[gene_id])[
                        "viennarna_version"
                    ],
                    rnaplfold_window=self.profiler.window,
                    rnaplfold_max_span=self.profiler.max_span,
                    rnaplfold_unpaired=self.profiler.unpaired,
                    rnaplfold_temperature_celsius=self.profiler.temperature_celsius,
                )
            return cache[key]

        plan = [
            (family, TriggerSet(activators=(candidate(ga, a0, a1), candidate(gb, b0, b1))))
            for _, family, ga, a0, a1, gb, b0, b1 in taken
        ]
        return plan, {
            "pair_ranking": "min_of_two_window_mean_marginal_unpaired_probabilities",
            "candidate_accessibility": "minimum_per_base_marginal_unpaired_probability",
            "discovered_pairs": discovered,
            "screened_pairs": screened,
            "eligible_pairs": len(eligible),
            "selected_pairs": len(plan),
            "discovery_truncated": discovery_truncated,
            "seed_matches_considered": seed_matches,
            "discovery_scopes": discovery_scopes,
            "pair_selection": settings.pair_selection,
            "accessibility_percentile": settings.accessibility_percentile,
            "percentile_cutoff": cutoff,
        }

    def score(
        self,
        genes: list[SelectedGene],
        sequences: dict[str, str],
        constraints: Constraints,
    ) -> Iterator[TriggerCandidate]:
        """Yield a stable per-gene shortlist across all configured footprint buckets."""
        joint_probability = getattr(self.profiler, "joint_probability", None)
        unsupported = sorted(set(constraints.trigger_lengths) - self.ALLOWED_SCANNED_LENGTHS)
        if callable(joint_probability) and unsupported:
            raise ValueError(
                # Derived from the mapping, never spelled out: the old message named
                # "30, 33, and 36" while the set it describes lives one attribute away,
                # so adding a footprint silently made the message wrong.
                "Gate-aware transcript scanning requires trigger_lengths to contain only "
                "the exact supported footprints "
                + ", ".join(str(n) for n in sorted(self.ALLOWED_SCANNED_LENGTHS))
                + " nt; unsupported: "
                + ", ".join(map(str, unsupported))
                + "."
            )

        for gene in genes:
            transcript = sequences[gene.gene_id]
            profile = self.profiler.profile(transcript)
            buckets: dict[int, list[TriggerCandidate]] = {
                length: [] for length in constraints.trigger_lengths
            }

            for length in constraints.trigger_lengths:
                for start, window in sq.windows(transcript, length):
                    if self.screener.violations(window):
                        continue
                    end = start + length
                    local_profile = profile[start:end]
                    openness = sum(local_profile) / length
                    accessibility = min(local_profile)

                    gate_evidence = self._gate_evidence(transcript, profile, start, end)
                    score = gate_evidence.get("selected_seed_probability", openness)
                    buckets[length].append(
                        TriggerCandidate(
                            trigger_id=f"trig-{gene.gene_id}-{start}-{length}",
                            gene_id=gene.gene_id,
                            symbol=gene.symbol,
                            sequence=window,
                            start_index=start,
                            openness=openness,
                            accessibility=accessibility,
                            mfe=self.folder.mfe(window).energy,
                            gc_content=sq.gc_content(window),
                            # The gene's, not the window's — read, never recomputed.
                            log2_fold_change=gene.log2_fold_change,
                            aug_indexes=sq.find_augs(window),
                            stop_indexes=sq.find_stops(window),
                            score=score,
                            **gate_evidence,
                        )
                    )

            gate_aware = any(
                candidate.gate_toehold_length is not None
                for candidates in buckets.values()
                for candidate in candidates
            )
            for candidates in buckets.values():
                candidates.sort(key=self._gate_rank_key if gate_aware else self._legacy_rank_key)
            yield from self._allocate_buckets(buckets, constraints.trigger_lengths)

    def _gate_evidence(
        self, transcript: str, profile: list[float], start: int, end: int
    ) -> dict[str, object]:
        length = end - start
        toehold_length = self.FOOTPRINT_TO_TOEHOLD.get(length)
        if toehold_length is None or not callable(
            getattr(self.profiler, "joint_probability", None)
        ):
            return {}

        provenance = self.profiler.provenance(transcript)
        hypothesis_start = end - self.HYPOTHESIS_LENGTH
        p20 = self.profiler.joint_probability(transcript, hypothesis_start, end)
        marginal20 = profile[hypothesis_start:end]
        mean20 = sum(marginal20) / self.HYPOTHESIS_LENGTH
        delta_g = -(
            self.GAS_CONSTANT_KCAL_PER_MOL_K
            * (provenance["temperature_celsius"] + 273.15)
            * math.log(max(p20, self.PU_FLOOR))
            / self.HYPOTHESIS_LENGTH
        )

        toehold_start = end - toehold_length
        trials = tuple(
            SeedOpeningTrial(
                start=seed_start,
                end=seed_start + self.SEED_LENGTH,
                relative_start=seed_start - toehold_start,
                sequence=transcript[seed_start : seed_start + self.SEED_LENGTH],
                probability=self.profiler.joint_probability(
                    transcript, seed_start, seed_start + self.SEED_LENGTH
                ),
            )
            for seed_start in range(toehold_start, end - self.SEED_LENGTH + 1)
        )
        # max() keeps the first item on ties, and trials are transcript-forward earliest first.
        selected = max(trials, key=lambda trial: trial.probability)
        return {
            "gate_toehold_length": toehold_length,
            "hypothesis_start": hypothesis_start,
            "hypothesis_end": end,
            "joint_open_probability_20": p20,
            "mean_marginal_openness_20": mean20,
            "delta_g_open_kcal_per_mol_per_nt": delta_g,
            "selected_seed_start": selected.start,
            "selected_seed_end": selected.end,
            "selected_seed_probability": selected.probability,
            "seed_trials": trials,
            "rnaplfold_version": provenance["viennarna_version"],
            "rnaplfold_window": provenance["window"],
            "rnaplfold_max_span": provenance["max_span"],
            "rnaplfold_unpaired": provenance["unpaired"],
            "rnaplfold_temperature_celsius": provenance["temperature_celsius"],
            "rnaplfold_model": (
                json.dumps(provenance["folding_model"], sort_keys=True, allow_nan=False)
                if "folding_model" in provenance
                else None
            ),
        }

    @staticmethod
    def _gate_rank_key(candidate: TriggerCandidate) -> tuple:
        if candidate.gate_toehold_length is None:
            return (
                1,
                -candidate.openness,
                -candidate.accessibility,
                candidate.start_index,
                candidate.sequence,
            )
        return (
            0,
            -candidate.selected_seed_probability,
            candidate.delta_g_open_kcal_per_mol_per_nt,
            -candidate.mean_marginal_openness_20,
            candidate.start_index,
            candidate.sequence,
        )

    @staticmethod
    def _legacy_rank_key(candidate: TriggerCandidate) -> tuple:
        return (
            -candidate.openness,
            -candidate.accessibility,
            candidate.start_index,
            candidate.sequence,
        )

    def _allocate_buckets(
        self, buckets: dict[int, list[TriggerCandidate]], order: tuple[int, ...]
    ) -> Iterator[TriggerCandidate]:
        """Round-robin bucket union in configured order, capped by TOP_K_PER_GENE."""
        emitted = 0
        index = 0
        while emitted < self.TOP_K_PER_GENE:
            added = False
            for length in order:
                candidates = buckets[length]
                if index < len(candidates):
                    yield candidates[index]
                    emitted += 1
                    added = True
                    if emitted == self.TOP_K_PER_GENE:
                        return
            if not added:
                return
            index += 1
