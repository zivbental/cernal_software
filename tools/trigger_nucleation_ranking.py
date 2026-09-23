"""Reusable ranking for marginal trigger/nucleation accessibility analyses.

This module ranks already-computed per-base marginal P(unpaired) evidence. It does not
replace the production gate-aware ``TriggerScorer`` and does not compute joint opening
probabilities.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import struct
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from io import StringIO
from pathlib import Path


class RankingMode(StrEnum):
    """Supported deterministic trigger/nucleation ranking modes."""

    NUCLEATION_FIRST = "nucleation_first"
    BALANCED_GEOMETRIC_MEAN = "balanced_geometric_mean"


@dataclass(frozen=True, slots=True)
class TriggerNucleationCandidate:
    """One trigger window and its selected nested nucleation window."""

    candidate_id: str
    start_1based: int
    end_1based: int
    target_rna_5to3: str
    full_trigger_mean_marginal_pu: float
    full_trigger_min_marginal_pu: float
    nucleation_start_1based: int
    nucleation_end_1based: int
    nucleation_rna_5to3: str
    nucleation_mean_marginal_pu: float
    nucleation_min_marginal_pu: float


@dataclass(frozen=True, slots=True)
class RankedTriggerNucleationCandidate:
    """A candidate with both the selected rank and preserved primary rank."""

    rank: int
    ranking_mode: RankingMode
    ranking_score: float
    balanced_geometric_mean: float
    nucleation_first_rank: int
    candidate: TriggerNucleationCandidate


@dataclass(frozen=True, slots=True)
class TriggerNucleationAnalysis:
    """Ranked candidates and deterministic provenance for one profile."""

    candidates: tuple[RankedTriggerNucleationCandidate, ...]
    provenance: dict[str, object]


def _probability(value: float, label: str) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{label} must be finite and within [0, 1].")


def _validate_candidate(candidate: TriggerNucleationCandidate) -> None:
    if not candidate.candidate_id:
        raise ValueError("Candidate IDs must be non-empty and unique.")
    if candidate.end_1based - candidate.start_1based + 1 != len(candidate.target_rna_5to3):
        raise ValueError(f"Trigger coordinates do not match {candidate.candidate_id!r}.")
    if candidate.nucleation_end_1based - candidate.nucleation_start_1based + 1 != len(
        candidate.nucleation_rna_5to3
    ):
        raise ValueError(f"Nucleation coordinates do not match {candidate.candidate_id!r}.")
    if not (
        candidate.start_1based
        <= candidate.nucleation_start_1based
        <= candidate.nucleation_end_1based
        <= candidate.end_1based
    ):
        raise ValueError(f"Nucleation window is not nested for {candidate.candidate_id!r}.")
    for label, value in (
        ("full-trigger mean marginal P(unpaired)", candidate.full_trigger_mean_marginal_pu),
        ("full-trigger minimum marginal P(unpaired)", candidate.full_trigger_min_marginal_pu),
        ("nucleation mean marginal P(unpaired)", candidate.nucleation_mean_marginal_pu),
        ("nucleation minimum marginal P(unpaired)", candidate.nucleation_min_marginal_pu),
    ):
        _probability(value, label)


def _nucleation_first_key(candidate: TriggerNucleationCandidate) -> tuple[object, ...]:
    return (
        -candidate.nucleation_mean_marginal_pu,
        -candidate.full_trigger_mean_marginal_pu,
        -candidate.full_trigger_min_marginal_pu,
        candidate.start_1based,
        candidate.target_rna_5to3,
    )


def rank_candidates(
    candidates: Iterable[TriggerNucleationCandidate],
    mode: RankingMode | str = RankingMode.NUCLEATION_FIRST,
) -> tuple[RankedTriggerNucleationCandidate, ...]:
    """Rank candidates deterministically without changing nucleation-first semantics."""
    selected_mode = RankingMode(mode)
    materialized = tuple(candidates)
    for candidate in materialized:
        _validate_candidate(candidate)
    candidate_ids = [candidate.candidate_id for candidate in materialized]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("Candidate IDs must be unique.")

    nucleation_first = sorted(materialized, key=_nucleation_first_key)
    primary_ranks = {
        candidate.candidate_id: rank for rank, candidate in enumerate(nucleation_first, start=1)
    }
    if selected_mode is RankingMode.NUCLEATION_FIRST:
        ordered = nucleation_first
    else:
        ordered = sorted(
            materialized,
            key=lambda candidate: (
                -math.sqrt(
                    candidate.full_trigger_mean_marginal_pu * candidate.nucleation_mean_marginal_pu
                ),
                -min(
                    candidate.full_trigger_mean_marginal_pu,
                    candidate.nucleation_mean_marginal_pu,
                ),
                -candidate.full_trigger_mean_marginal_pu,
                -candidate.nucleation_mean_marginal_pu,
                primary_ranks[candidate.candidate_id],
                candidate.start_1based,
                candidate.target_rna_5to3,
            ),
        )

    rows = []
    for rank, candidate in enumerate(ordered, start=1):
        balanced = math.sqrt(
            candidate.full_trigger_mean_marginal_pu * candidate.nucleation_mean_marginal_pu
        )
        score = (
            candidate.nucleation_mean_marginal_pu
            if selected_mode is RankingMode.NUCLEATION_FIRST
            else balanced
        )
        rows.append(
            RankedTriggerNucleationCandidate(
                rank=rank,
                ranking_mode=selected_mode,
                ranking_score=score,
                balanced_geometric_mean=balanced,
                nucleation_first_rank=primary_ranks[candidate.candidate_id],
                candidate=candidate,
            )
        )
    return tuple(rows)


def _profile_sha256(values: tuple[float, ...]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(struct.pack(">d", value))
    return digest.hexdigest()


def _tie_breaks(mode: RankingMode) -> list[str]:
    if mode is RankingMode.NUCLEATION_FIRST:
        return [
            "higher selected nucleation mean marginal P(unpaired)",
            "higher full-trigger mean marginal P(unpaired)",
            "higher full-trigger minimum marginal P(unpaired)",
            "earlier trigger start",
            "lexicographically earlier target RNA sequence",
        ]
    return [
        "higher geometric mean sqrt(full-trigger mean * nucleation mean)",
        "higher minimum of the two mean components",
        "higher full-trigger mean marginal P(unpaired)",
        "higher selected nucleation mean marginal P(unpaired)",
        "lower preserved nucleation-first rank",
        "earlier trigger start",
        "lexicographically earlier target RNA sequence",
    ]


def analyze_profile(
    sequence: str,
    profile: Iterable[float],
    *,
    trigger_length: int,
    nucleation_length: int,
    stride: int = 1,
    mode: RankingMode | str = RankingMode.NUCLEATION_FIRST,
    source_provenance: Mapping[str, object] | None = None,
) -> TriggerNucleationAnalysis:
    """Enumerate trigger windows and rank their best nested nucleation windows."""
    invalid = sorted(set(sequence) - set("ACGU"))
    if not sequence or invalid:
        suffix = f" Invalid symbols: {', '.join(invalid)}." if invalid else ""
        raise ValueError("Sequence must be non-empty uppercase RNA A/C/G/U." + suffix)
    if type(trigger_length) is not int or type(nucleation_length) is not int:
        raise ValueError("Trigger and nucleation lengths must be integers.")
    if not 1 <= nucleation_length <= trigger_length <= len(sequence):
        raise ValueError("Require 1 <= nucleation_length <= trigger_length <= sequence length.")
    if type(stride) is not int or stride < 1:
        raise ValueError("stride must be a positive integer.")

    values = tuple(float(value) for value in profile)
    if len(values) != len(sequence):
        raise ValueError("RNAplfold profile length must equal sequence length.")
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in values):
        raise ValueError("Marginal P(unpaired) values must be finite and within [0, 1].")

    candidates = []
    starts = range(0, len(sequence) - trigger_length + 1, stride)
    for start0 in starts:
        end0 = start0 + trigger_length
        trigger_values = values[start0:end0]
        local = []
        for nucleation_start0 in range(start0, end0 - nucleation_length + 1):
            nucleation_end0 = nucleation_start0 + nucleation_length
            nucleation_values = values[nucleation_start0:nucleation_end0]
            local.append((sum(nucleation_values) / nucleation_length, nucleation_start0))
        nucleation_mean, nucleation_start0 = max(local, key=lambda item: (item[0], -item[1]))
        nucleation_end0 = nucleation_start0 + nucleation_length
        candidates.append(
            TriggerNucleationCandidate(
                candidate_id=f"cand-{start0 + 1:04d}-{end0:04d}",
                start_1based=start0 + 1,
                end_1based=end0,
                target_rna_5to3=sequence[start0:end0],
                full_trigger_mean_marginal_pu=sum(trigger_values) / trigger_length,
                full_trigger_min_marginal_pu=min(trigger_values),
                nucleation_start_1based=nucleation_start0 + 1,
                nucleation_end_1based=nucleation_end0,
                nucleation_rna_5to3=sequence[nucleation_start0:nucleation_end0],
                nucleation_mean_marginal_pu=nucleation_mean,
                nucleation_min_marginal_pu=min(values[nucleation_start0:nucleation_end0]),
            )
        )

    selected_mode = RankingMode(mode)
    ranked = rank_candidates(candidates, selected_mode)
    provenance: dict[str, object] = {
        "schema_version": 1,
        "analysis_type": "trigger_nucleation_marginal_accessibility_ranking",
        "implementation": "tools.trigger_nucleation_ranking",
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "sequence_sha256_exact_ascii": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
        "profile_sha256_float64_be": _profile_sha256(values),
        "sequence_length": len(sequence),
        "trigger_length": trigger_length,
        "nucleation_length": nucleation_length,
        "stride": stride,
        "candidate_count": len(ranked),
        "expected_candidate_count": (len(sequence) - trigger_length) // stride + 1,
        "ranking_mode": selected_mode.value,
        "tie_breaks": _tie_breaks(selected_mode),
        "orientation": "supplied target/sense RNA in provided 5prime-to-3prime order",
        "coordinate_convention": (
            "one-based inclusive in outputs; zero-based half-open internally"
        ),
        "profile_semantics": (
            "arithmetic aggregates of standalone one-base marginal P(unpaired) values"
        ),
        "nucleation_placement": (
            "best internal contiguous window by mean marginal P(unpaired); earliest "
            "5prime start on exact ties"
        ),
        "joint_probability_used": False,
        "normalization_applied": False,
        "balanced_question": (
            "balanced_geometric_mean asks which candidate jointly keeps full-trigger and "
            "nucleation mean marginal accessibility high; it is a separate sensitivity "
            "ranking, not a replacement for nucleation_first"
        ),
        "source_provenance": dict(source_provenance or {}),
    }
    return TriggerNucleationAnalysis(candidates=ranked, provenance=provenance)


def analysis_rows(analysis: TriggerNucleationAnalysis) -> tuple[dict[str, object], ...]:
    """Flatten ranked candidates into stable CSV-ready dictionaries."""
    rows = []
    for ranked in analysis.candidates:
        candidate = ranked.candidate
        rows.append(
            {
                "rank": ranked.rank,
                "ranking_mode": ranked.ranking_mode.value,
                "ranking_score": ranked.ranking_score,
                "balanced_geometric_mean": ranked.balanced_geometric_mean,
                "nucleation_first_rank": ranked.nucleation_first_rank,
                "candidate_id": candidate.candidate_id,
                "start_1based": candidate.start_1based,
                "end_1based": candidate.end_1based,
                "target_rna_5to3": candidate.target_rna_5to3,
                "full_trigger_mean_marginal_pu": candidate.full_trigger_mean_marginal_pu,
                "full_trigger_min_marginal_pu": candidate.full_trigger_min_marginal_pu,
                "nucleation_start_1based": candidate.nucleation_start_1based,
                "nucleation_end_1based": candidate.nucleation_end_1based,
                "nucleation_rna_5to3": candidate.nucleation_rna_5to3,
                "nucleation_mean_marginal_pu": candidate.nucleation_mean_marginal_pu,
                "nucleation_min_marginal_pu": candidate.nucleation_min_marginal_pu,
            }
        )
    return tuple(rows)


def _write_text(path: str | Path, text: str, *, overwrite: bool) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "x"
    with destination.open(mode, encoding="utf-8", newline="") as handle:
        handle.write(text)


def write_analysis_csv(
    analysis: TriggerNucleationAnalysis, path: str | Path, *, overwrite: bool = False
) -> None:
    """Write a complete ranked table, refusing accidental overwrite by default."""
    rows = analysis_rows(analysis)
    if not rows:
        raise ValueError("Cannot write an analysis with no candidates.")
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    _write_text(path, buffer.getvalue(), overwrite=overwrite)


def write_provenance_json(
    analysis: TriggerNucleationAnalysis, path: str | Path, *, overwrite: bool = False
) -> None:
    """Write deterministic provenance, refusing accidental overwrite by default."""
    text = json.dumps(analysis.provenance, indent=2, sort_keys=True) + "\n"
    _write_text(path, text, overwrite=overwrite)
