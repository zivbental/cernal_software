"""Stage 2 — gate-aware trigger selection in transcript context.

Exact 30/33/36-nt windows map to the CERNAL 12/15/18-nt toehold variants.  RNAplfold
joint opening probabilities are mechanistic hypotheses, not biological-success
probabilities.  Mean marginal openness is retained as diagnostic evidence.
"""

import math
from collections.abc import Iterator

from engine import sequences as sq
from engine.domain import (
    Constraints,
    SeedOpeningTrial,
    SelectedGene,
    TriggerCandidate,
)
from engine.gates.tools.folding import FoldEngine
from engine.stages.folding import FoldProfiler
from engine.stages.motifs import MotifScreener
from engine.stages.off_target import OffTargetScanner


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
    FOOTPRINT_TO_TOEHOLD = {30: 12, 33: 15, 36: 18}
    ALLOWED_SCANNED_LENGTHS = frozenset(FOOTPRINT_TO_TOEHOLD)
    HYPOTHESIS_LENGTH = 20
    SEED_LENGTH = 8
    GAS_CONSTANT_KCAL_PER_MOL_K = 0.00198720425864083
    TEMPERATURE_K = 310.15
    PU_FLOOR = 1e-12

    def __init__(
        self,
        profiler: FoldProfiler,
        off_target: OffTargetScanner,
        screener: MotifScreener,
        folder: FoldEngine,
    ) -> None:
        self.profiler = profiler
        self.off_target = off_target
        self.screener = screener
        self.folder = folder

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
                "Gate-aware transcript scanning requires trigger_lengths to contain only "
                "the exact supported footprints 30, 33, and 36 nt; unsupported: "
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
                    off_target_report = self.off_target.scan_trigger(window)
                    segment_specificity = max(0.0, 1.0 - off_target_report.penalty)

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
                            off_target_penalty=off_target_report.penalty,
                            segment_specificity=segment_specificity,
                            gc_content=sq.gc_content(window),
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

        hypothesis_start = end - self.HYPOTHESIS_LENGTH
        p20 = self.profiler.joint_probability(transcript, hypothesis_start, end)
        marginal20 = profile[hypothesis_start:end]
        mean20 = sum(marginal20) / self.HYPOTHESIS_LENGTH
        delta_g = -(
            self.GAS_CONSTANT_KCAL_PER_MOL_K
            * self.TEMPERATURE_K
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
        provenance = self.profiler.provenance(transcript)
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
