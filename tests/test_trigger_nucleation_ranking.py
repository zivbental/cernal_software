from tools.trigger_nucleation_ranking import (
    RankingMode,
    TriggerNucleationCandidate,
    rank_candidates,
)


def candidate(
    candidate_id: str,
    *,
    start: int,
    full: float,
    nucleation: float,
    full_min: float = 0.1,
) -> TriggerNucleationCandidate:
    sequence = "A" * 4
    return TriggerNucleationCandidate(
        candidate_id=candidate_id,
        start_1based=start,
        end_1based=start + 3,
        target_rna_5to3=sequence,
        full_trigger_mean_marginal_pu=full,
        full_trigger_min_marginal_pu=full_min,
        nucleation_start_1based=start,
        nucleation_end_1based=start + 1,
        nucleation_rna_5to3="AA",
        nucleation_mean_marginal_pu=nucleation,
        nucleation_min_marginal_pu=min(nucleation, full_min),
    )


def test_default_ranking_preserves_lexicographic_nucleation_first_semantics():
    candidates = [
        candidate("earlier", start=1, full=0.6, nucleation=0.8, full_min=0.2),
        candidate("higher-full", start=2, full=0.7, nucleation=0.8, full_min=0.1),
        candidate("higher-nucleation", start=3, full=0.2, nucleation=0.9),
    ]

    ranked = rank_candidates(candidates)

    assert [row.candidate.candidate_id for row in ranked] == [
        "higher-nucleation",
        "higher-full",
        "earlier",
    ]
    assert [row.rank for row in ranked] == [1, 2, 3]
    assert all(row.ranking_mode is RankingMode.NUCLEATION_FIRST for row in ranked)
    assert [row.nucleation_first_rank for row in ranked] == [1, 2, 3]


def test_balanced_geometric_mean_is_explicit_and_can_change_the_winner():
    candidates = [
        candidate("nucleation-only", start=1, full=0.2, nucleation=1.0),
        candidate("balanced", start=2, full=0.8, nucleation=0.8),
    ]

    primary = rank_candidates(candidates)
    balanced = rank_candidates(candidates, RankingMode.BALANCED_GEOMETRIC_MEAN)

    assert [row.candidate.candidate_id for row in primary] == [
        "nucleation-only",
        "balanced",
    ]
    assert [row.candidate.candidate_id for row in balanced] == [
        "balanced",
        "nucleation-only",
    ]
    assert balanced[0].ranking_score == 0.8
    assert balanced[0].nucleation_first_rank == 2
    assert balanced[1].nucleation_first_rank == 1


def test_analyze_profile_enumerates_dense_coordinates_and_uses_earliest_nucleation_tie():
    from tools.trigger_nucleation_ranking import analyze_profile

    analysis = analyze_profile(
        "ACGUA",
        [0.9, 0.1, 0.9, 0.1, 0.9],
        trigger_length=4,
        nucleation_length=2,
    )

    assert [row.candidate.candidate_id for row in analysis.candidates] == [
        "cand-0001-0004",
        "cand-0002-0005",
    ]
    first = analysis.candidates[0].candidate
    assert (first.start_1based, first.end_1based) == (1, 4)
    assert first.target_rna_5to3 == "ACGU"
    assert (first.nucleation_start_1based, first.nucleation_end_1based) == (1, 2)
    assert first.nucleation_rna_5to3 == "AC"
    assert first.full_trigger_mean_marginal_pu == 0.5
    assert first.nucleation_mean_marginal_pu == 0.5
    assert analysis.provenance["candidate_count"] == 2
    assert analysis.provenance["expected_candidate_count"] == 2
    assert analysis.provenance["ranking_mode"] == "nucleation_first"


def test_analysis_rejects_invalid_sequence_profile_and_window_configuration():
    import pytest
    from tools.trigger_nucleation_ranking import analyze_profile

    with pytest.raises(ValueError, match="uppercase RNA"):
        analyze_profile("ACGT", [0.5] * 4, trigger_length=4, nucleation_length=2)
    with pytest.raises(ValueError, match="profile length"):
        analyze_profile("ACGU", [0.5] * 3, trigger_length=4, nucleation_length=2)
    with pytest.raises(ValueError, match=r"finite and within \[0, 1\]"):
        analyze_profile(
            "ACGU",
            [0.5, float("nan"), 0.5, 0.5],
            trigger_length=4,
            nucleation_length=2,
        )
    with pytest.raises(ValueError, match="1 <= nucleation_length"):
        analyze_profile("ACGU", [0.5] * 4, trigger_length=3, nucleation_length=4)
    with pytest.raises(ValueError, match="stride"):
        analyze_profile("ACGU", [0.5] * 4, trigger_length=4, nucleation_length=2, stride=0)


def test_provenance_hashes_exact_inputs_and_records_semantics_without_a_timestamp():
    import hashlib

    from tools.trigger_nucleation_ranking import RankingMode, analyze_profile

    analysis = analyze_profile(
        "ACGUA",
        [0.9, 0.1, 0.9, 0.1, 0.9],
        trigger_length=4,
        nucleation_length=2,
        mode=RankingMode.BALANCED_GEOMETRIC_MEAN,
        source_provenance={"git_commit": "abc123", "rnaplfold": {"window": 5}},
    )

    provenance = analysis.provenance
    assert provenance["sequence_sha256_exact_ascii"] == hashlib.sha256(b"ACGUA").hexdigest()
    assert len(provenance["profile_sha256_float64_be"]) == 64
    assert len(provenance["implementation_sha256"]) == 64
    assert provenance["source_provenance"] == {
        "git_commit": "abc123",
        "rnaplfold": {"window": 5},
    }
    assert provenance["ranking_mode"] == "balanced_geometric_mean"
    assert provenance["joint_probability_used"] is False
    assert provenance["normalization_applied"] is False
    assert "created_utc" not in provenance


def test_rank_candidates_rejects_duplicate_candidate_ids():
    import pytest

    with pytest.raises(ValueError, match="unique"):
        rank_candidates(
            [
                candidate("duplicate", start=1, full=0.5, nucleation=0.5),
                candidate("duplicate", start=2, full=0.6, nucleation=0.6),
            ]
        )


def test_analysis_rows_and_writers_emit_reviewable_small_artifacts(tmp_path):
    import csv
    import json

    import pytest
    from tools.trigger_nucleation_ranking import (
        analysis_rows,
        analyze_profile,
        write_analysis_csv,
        write_provenance_json,
    )

    analysis = analyze_profile(
        "ACGUA",
        [0.9, 0.1, 0.9, 0.1, 0.9],
        trigger_length=4,
        nucleation_length=2,
    )
    rows = analysis_rows(analysis)
    assert rows[0]["rank"] == 1
    assert rows[0]["ranking_mode"] == "nucleation_first"
    assert rows[0]["nucleation_first_rank"] == 1
    assert rows[0]["candidate_id"] == "cand-0001-0004"

    csv_path = tmp_path / "ranked.csv"
    provenance_path = tmp_path / "provenance.json"
    write_analysis_csv(analysis, csv_path)
    write_provenance_json(analysis, provenance_path)

    with csv_path.open(newline="", encoding="utf-8") as handle:
        written_rows = list(csv.DictReader(handle))
    assert len(written_rows) == 2
    assert written_rows[0]["candidate_id"] == "cand-0001-0004"
    assert json.loads(provenance_path.read_text())["candidate_count"] == 2
    with pytest.raises(FileExistsError):
        write_analysis_csv(analysis, csv_path)
