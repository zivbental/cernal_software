"""Stage 2 — gate-aware trigger selection in transcript context.

Exact 30/33/36-nt windows map to the CERNAL 12/15/18-nt toehold variants.  RNAplfold
joint opening probabilities are mechanistic hypotheses, not biological-success
probabilities.  Mean marginal openness is retained as diagnostic evidence.
"""

import json
import math
import random
from collections import Counter
from collections.abc import Callable, Iterator
from itertools import combinations

from engine import sequences as sq
from engine.domain import (
    Constraints,
    ProkaryoticAndSettings,
    SeedOpeningTrial,
    SelectedGene,
    TriggerCandidate,
    TriggerSet,
)
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
        windows: list[TriggerCandidate],
        sequences: dict[str, str],
        families: list,
        settings: ProkaryoticAndSettings,
        constraints: Constraints,
        *,
        seed: int,
        on_progress: Callable[[int, int], bool] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> tuple[list[tuple[str, TriggerSet]], dict]:
        """Find overlaps only inside CERNAL's nominated accessible regions.

        Maximal reverse-complementary runs (>= MIN_OVERLAP) nominate new role-specific
        footprints, which may extend outside those regions but must fit the transcript.
        Rescore those exact intervals with the upstream gate-aware scoring method.
        Pair order uses the lower of the two trigger scores; percentile sampling is a
        declared search policy, not a biological feasibility threshold.
        """
        by_gene: dict[str, list[TriggerCandidate]] = {}
        for window in windows:
            transcript = sequences[window.gene_id]
            start, end = window.start_index, window.start_index + len(window.sequence)
            if transcript[start:end] != window.sequence:
                raise ValueError("Upstream trigger coordinates do not match the transcript.")
            by_gene.setdefault(window.gene_id, []).append(window)
        regions = {
            gene: tuple((w.start_index, w.start_index + len(w.sequence)) for w in pool)
            for gene, pool in by_gene.items()
        }
        cache = {}
        profiles = {}
        originals = {
            (w.gene_id, w.start_index, w.start_index + len(w.sequence), w.gate_toehold_length): w
            for w in windows
        }

        def candidate(gene_id, start, end, toehold_length):
            key = gene_id, start, end, toehold_length
            if key in originals:
                return originals[key]
            if key not in cache:
                if gene_id not in profiles:
                    profiles[gene_id] = self.profiler.profile(sequences[gene_id])
                cache[key] = self.score_window(
                    by_gene[gene_id][0],
                    sequences[gene_id],
                    start,
                    end,
                    profile=profiles[gene_id],
                    toehold_length=toehold_length,
                )
            return cache[key]

        rows = []
        seen = set()
        discovered = screened = seed_matches = 0
        truncated = False
        scopes = []
        stop = should_stop or (lambda: False)
        for first, second in combinations(sorted(by_gene), 2):
            if stop() or truncated:
                break
            for family in families:
                remaining = settings.max_pair_seed_matches - seed_matches
                if remaining <= 0 or stop():
                    truncated = True
                    break
                source = family.find_cross_gene_pairs(
                    first,
                    sequences[first],
                    second,
                    sequences[second],
                    regions_a=regions[first],
                    regions_b=regions[second],
                    max_matches=remaining,
                    on_progress=on_progress,
                )
                for pair in source:
                    if discovered >= settings.max_pair_candidates or stop():
                        truncated = True
                        break
                    ga, gb = pair.gene_a, pair.gene_b
                    a0, a1 = pair.window_a()
                    b0, b1 = pair.window_b()
                    key = family.geometry_name, ga, a0, a1, gb, b0, b1
                    if key in seen:
                        continue
                    seen.add(key)
                    discovered += 1
                    if (
                        not constraints.overlap_range[0]
                        <= pair.len_x
                        <= constraints.overlap_range[1]
                    ):
                        screened += 1
                        continue
                    if any(
                        self.screener.violations(sequences[g][lo:hi])
                        for g, lo, hi in ((ga, a0, a1), (gb, b0, b1))
                    ):
                        screened += 1
                        continue
                    a = candidate(ga, a0, a1, family.SECONDARY_INVASION_LEN)
                    b = candidate(gb, b0, b1, family.TOEHOLD_B_LEN)
                    rows.append((min(a.score, b.score), key, a, b, pair.len_x))
                scope = dict(family.last_pair_search)
                seed_matches += scope["seed_matches_considered"]
                scopes.append({"genes": [first, second], "geometry": family.geometry_name, **scope})
                truncated |= scope["discovery_truncated"]
                if truncated:
                    break
        rows.sort(key=lambda row: (-row[0], row[1]))
        cutoff = None
        eligible = rows
        if settings.pair_selection == "percentile_sample" and rows:
            ascending = sorted(row[0] for row in rows)
            index = min(
                len(rows) - 1,
                max(0, math.ceil(settings.accessibility_percentile / 100 * len(rows)) - 1),
            )
            cutoff = ascending[index]
            eligible = [row for row in rows if row[0] >= cutoff]
            taken = random.Random(seed).sample(eligible, min(settings.max_pairs, len(eligible)))
            taken.sort(key=lambda row: (-row[0], row[1]))
        elif settings.pair_selection == "overlap_stratified":
            taken = self._overlap_stratified_pairs(rows, settings.max_pairs)
        else:
            taken = rows[: settings.max_pairs]
        plan = [(key[0], TriggerSet(activators=(a, b))) for _, key, a, b, _length in taken]
        return plan, {
            "input_regions": len(windows),
            "input_genes": len(by_gene),
            "input_region_coordinates": {gene: list(spans) for gene, spans in regions.items()},
            "search_scope": "overlaps_within_upstream_regions_footprints_within_transcripts",
            "pair_ranking": "min_of_two_cernal_gate_aware_trigger_scores",
            "trigger_selection_method": self.SELECTION_METHOD,
            "candidate_accessibility": "minimum_per_base_marginal_unpaired_probability",
            "rescored_footprints": len(cache),
            "discovered_pairs": discovered,
            "screened_pairs": screened,
            "eligible_pairs": len(eligible),
            "selected_pairs": len(plan),
            "discovery_truncated": truncated or stop(),
            "seed_matches_considered": seed_matches,
            "discovery_scopes": scopes,
            "pair_selection": settings.pair_selection,
            "eligible_overlap_distribution": dict(sorted(Counter(r[4] for r in eligible).items())),
            "selected_overlap_distribution": dict(sorted(Counter(r[4] for r in taken).items())),
            "overlap_coverage_complete": {r[4] for r in eligible} == {r[4] for r in taken},
            "accessibility_percentile": settings.accessibility_percentile,
            "percentile_cutoff": cutoff,
        }

    @staticmethod
    def _overlap_stratified_pairs(rows: list, limit: int) -> list:
        """Retain length coverage and approximate pool proportions, ranking within lengths.

        Rows are already ordered by descending minimum partner score and stable coordinates.
        Reserve one slot per observed length when possible. Allocate each remaining slot to
        the largest deficit from its proportional quota; ties use the next pair's rank.
        If fewer slots than lengths are available, represent the lengths with the best
        available pairs. Never infer a biological preference from overlap length.
        """
        if len(rows) <= limit:
            return rows
        groups = {}
        for rank, row in enumerate(rows):
            groups.setdefault(row[4], []).append((rank, row))
        quota = dict.fromkeys(groups, 0)
        for length in list(groups)[:limit]:
            quota[length] = 1
        for _ in range(limit - sum(quota.values())):
            length = max(
                (length for length, pool in groups.items() if quota[length] < len(pool)),
                key=lambda length: (
                    limit * len(groups[length]) - len(rows) * quota[length],
                    -groups[length][quota[length]][0],
                ),
            )
            quota[length] += 1
        selected = [item for length, pool in groups.items() for item in pool[: quota[length]]]
        return [row for _rank, row in sorted(selected, key=lambda item: item[0])]

    def score(
        self,
        genes: list[SelectedGene],
        sequences: dict[str, str],
        constraints: Constraints,
        *,
        should_stop: Callable[[], bool] | None = None,
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
                    if should_stop is not None and should_stop():
                        return
                    if self.screener.violations(window):
                        continue
                    buckets[length].append(
                        self.score_window(gene, transcript, start, start + length, profile=profile)
                    )

            gate_aware = any(
                candidate.gate_toehold_length is not None
                for candidates in buckets.values()
                for candidate in candidates
            )
            for candidates in buckets.values():
                candidates.sort(key=self._gate_rank_key if gate_aware else self._legacy_rank_key)
            yield from self._allocate_buckets(buckets, constraints.trigger_lengths)

    def score_window(
        self,
        gene: SelectedGene | TriggerCandidate,
        transcript: str,
        start: int,
        end: int,
        *,
        profile: list[float] | None = None,
        toehold_length: int | None = None,
    ) -> TriggerCandidate:
        """Score one exact footprint with the same method as upstream selection.

        AND footprints can extend beyond the region that nominated their overlap.
        They are new intervals, so their accessibility must be measured in transcript
        context rather than copied from the upstream region. Existing intervals retain
        their upstream records in the pair planner.
        """
        if not 0 <= start < end <= len(transcript):
            raise ValueError("Trigger footprint lies outside its transcript.")
        profile = self.profiler.profile(transcript) if profile is None else profile
        window = transcript[start:end]
        values = profile[start:end]
        openness = sum(values) / len(values)
        evidence = self._gate_evidence(
            transcript, profile, start, end, toehold_length=toehold_length
        )
        return TriggerCandidate(
            trigger_id=f"trig-{gene.gene_id}-{start}-{end - start}",
            gene_id=gene.gene_id,
            symbol=gene.symbol,
            sequence=window,
            start_index=start,
            openness=openness,
            accessibility=min(values),
            mfe=self.folder.mfe(window).energy,
            gc_content=sq.gc_content(window),
            log2_fold_change=gene.log2_fold_change,
            aug_indexes=sq.find_augs(window),
            stop_indexes=sq.find_stops(window),
            score=evidence.get("selected_seed_probability", openness),
            **evidence,
        )

    def _gate_evidence(
        self,
        transcript: str,
        profile: list[float],
        start: int,
        end: int,
        *,
        toehold_length: int | None = None,
    ) -> dict[str, object]:
        length = end - start
        if toehold_length is None:
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
