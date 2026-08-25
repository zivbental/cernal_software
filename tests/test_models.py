"""Domain model invariants (docs/software-design.md §5, §6).

Focused on the guarantees that would be expensive to lose: immutability of submitted
runs, rejected candidates keeping their reasons, and the state machine's shape.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.analyses.models import ALLOWED_TRANSITIONS, TERMINAL_STATUSES, AnalysisRun, RunStatus
from apps.datasets.models import Dataset, ValidationStatus
from apps.projects.models import Project
from apps.results.models import Candidate, CandidateMetric, MetricDirection


def _candidate(run, ref="c1", **kwargs):
    defaults = {"gate_family": "toehold", "logic_type": "AND"}
    defaults.update(kwargs)
    return Candidate.objects.create(run=run, engine_ref=ref, **defaults)


# --- Projects ---------------------------------------------------------------------


def test_project_names_are_unique_per_owner(user, project):
    with pytest.raises(IntegrityError):
        Project.objects.create(owner=user, name=project.name, organism="E. coli")


def test_two_owners_may_use_the_same_project_name(other_user, project):
    Project.objects.create(owner=other_user, name=project.name, organism="E. coli")


def test_deleting_a_user_with_projects_is_blocked(user, project):
    """PROTECT: deleting an account must not silently orphan its research."""
    with pytest.raises(IntegrityError):
        user.delete()


# --- Datasets ---------------------------------------------------------------------


def test_dataset_is_only_usable_once_validated(dataset):
    assert dataset.is_usable

    dataset.validation_status = ValidationStatus.INVALID
    assert not dataset.is_usable


def test_dataset_defaults_to_pending_validation(project, user):
    obj = Dataset.objects.create(project=project, name="x.csv", uploaded_by=user)
    assert obj.validation_status == ValidationStatus.PENDING


def test_dataset_file_is_namespaced_by_id(dataset):
    assert str(dataset.id) in dataset.file.name
    assert dataset.file.name.startswith("datasets/")


def test_dataset_referenced_by_a_run_cannot_be_deleted(run, dataset):
    """PROTECT: results must never outlive the input that produced them."""
    with pytest.raises(IntegrityError):
        dataset.delete()


# --- Run state machine ------------------------------------------------------------


def test_a_new_run_defaults_to_draft(project, dataset, user):
    obj = AnalysisRun.objects.create(
        project=project, dataset=dataset, created_by=user, idempotency_key="fresh"
    )
    assert obj.status == RunStatus.DRAFT
    assert obj.progress_pct == 0
    assert not obj.is_terminal


def test_terminal_statuses_have_no_outgoing_transitions():
    for status in TERMINAL_STATUSES:
        assert ALLOWED_TRANSITIONS[status] == frozenset(), f"{status} must be terminal"


def test_every_status_appears_in_the_transition_table():
    assert set(ALLOWED_TRANSITIONS) == {s.value for s in RunStatus}


@pytest.mark.parametrize(
    ("start", "target", "allowed"),
    [
        (RunStatus.DRAFT, RunStatus.QUEUED, True),
        (RunStatus.QUEUED, RunStatus.RUNNING, True),
        (RunStatus.RUNNING, RunStatus.COMPLETED, True),
        (RunStatus.RUNNING, RunStatus.FAILED, True),
        (RunStatus.QUEUED, RunStatus.CANCELLED, True),
        (RunStatus.DRAFT, RunStatus.RUNNING, False),
        (RunStatus.DRAFT, RunStatus.COMPLETED, False),
        (RunStatus.COMPLETED, RunStatus.RUNNING, False),
        (RunStatus.FAILED, RunStatus.QUEUED, False),
        (RunStatus.CANCELLED, RunStatus.RUNNING, False),
    ],
)
def test_transition_table(run, start, target, allowed):
    run.status = start
    assert run.can_transition_to(target) is allowed


def test_is_active_covers_exactly_the_in_flight_states(run):
    for status in (RunStatus.QUEUED, RunStatus.RUNNING):
        run.status = status
        assert run.is_active

    for status in (RunStatus.DRAFT, *TERMINAL_STATUSES):
        run.status = status
        assert not run.is_active


def test_idempotency_keys_are_unique(run, project, dataset, user):
    """Rule: a retried submission must not launch a second computation."""
    with pytest.raises(IntegrityError):
        AnalysisRun.objects.create(
            project=project,
            dataset=dataset,
            created_by=user,
            idempotency_key=run.idempotency_key,
        )


def test_progress_outside_zero_to_hundred_is_rejected_by_the_database(run):
    for bad in (-1, 101):
        with pytest.raises(IntegrityError), transaction.atomic():
            AnalysisRun.objects.filter(pk=run.pk).update(progress_pct=bad)


# --- Candidates -------------------------------------------------------------------


def test_a_rejected_candidate_without_a_reason_is_rejected_by_the_database(run):
    """Rule 8, enforced in the schema rather than by convention."""
    with pytest.raises(IntegrityError), transaction.atomic():
        _candidate(run, is_rejected=True, rejection_reason="")


def test_a_rejected_candidate_with_a_reason_is_accepted(run):
    candidate = _candidate(run, is_rejected=True, rejection_reason="Too leaky.")
    assert candidate.pk is not None


def test_a_rejected_candidate_cannot_hold_a_rank(run):
    with pytest.raises(IntegrityError), transaction.atomic():
        _candidate(run, is_rejected=True, rejection_reason="Too leaky.", rank=1)


def test_engine_ref_is_unique_within_a_run(run):
    _candidate(run, ref="dup")
    with pytest.raises(IntegrityError), transaction.atomic():
        _candidate(run, ref="dup")


def test_the_same_engine_ref_may_appear_in_different_runs(run, project, dataset, user):
    other = AnalysisRun.objects.create(
        project=project, dataset=dataset, created_by=user, idempotency_key="second"
    )
    _candidate(run, ref="cand-001")
    _candidate(other, ref="cand-001")


def test_candidates_default_to_rank_order(run):
    _candidate(run, ref="c3", rank=3)
    _candidate(run, ref="c1", rank=1)
    _candidate(run, ref="c2", rank=2)

    assert [c.engine_ref for c in run.candidates.all()] == ["c1", "c2", "c3"]


def test_deleting_a_run_removes_its_results(run):
    candidate = _candidate(run)
    CandidateMetric.objects.create(
        candidate=candidate, name="m", weight=1.0, direction=MetricDirection.HIGHER_BETTER
    )

    run.delete()

    assert Candidate.objects.count() == 0
    assert CandidateMetric.objects.count() == 0


def test_a_metric_name_appears_once_per_candidate(run):
    candidate = _candidate(run)
    CandidateMetric.objects.create(
        candidate=candidate, name="leak", weight=1.0, direction=MetricDirection.LOWER_BETTER
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CandidateMetric.objects.create(
            candidate=candidate, name="leak", weight=2.0, direction=MetricDirection.LOWER_BETTER
        )
