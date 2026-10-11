"""Global filters and history navigation must remain correct beyond the first page."""

from uuid import uuid4

import pytest

from apps.analyses.models import AnalysisRun
from apps.results.models import Candidate

pytestmark = pytest.mark.django_db


def test_global_filters_and_last_page(auth_client, user):
    run = AnalysisRun.objects.create(
        idempotency_key=str(uuid4()),
        created_by=user,
        input_mode="direct",
        trigger_sequence="ACGU" * 10,
    )
    Candidate.objects.bulk_create(
        [
            Candidate(
                run=run,
                engine_ref=f"cand-{index:05}",
                rank=index,
                overall_score=0.8,
                gate_family="toehold",
                logic_type="SINGLE",
                design={"logic_graph": {"output": "other" if index > 200 else "gfp"}},
            )
            for index in range(1, 7908)
        ]
    )
    url = f"/api/runs/{run.id}/candidates"
    page = auth_client.get(f"{url}?limit=50&offset=200").json()
    assert page["count"] == 7907
    assert page["items"][0]["rank"] == 201
    last = auth_client.get(f"{url}?limit=50&offset=7900").json()
    assert last["items"][-1]["rank"] == 7907
    filtered = auth_client.get(f"{url}?limit=50&output=other&min_score=.7").json()
    assert filtered["count"] == 7707
    assert filtered["items"][0]["rank"] == 201
    assert auth_client.get(f"{url}?min_score=.9").json()["count"] == 0
    assert auth_client.get(f"{url}?min_score=2").status_code == 422


def test_history_offset_remains_owned(auth_client, user, other_user):
    owned = [
        AnalysisRun.objects.create(
            idempotency_key=str(uuid4()),
            created_by=user,
            input_mode="direct",
            trigger_sequence="ACGU" * 10,
        )
        for _ in range(55)
    ]
    AnalysisRun.objects.create(
        idempotency_key=str(uuid4()),
        created_by=other_user,
        input_mode="direct",
        trigger_sequence="ACGU" * 10,
    )
    page = auth_client.get("/api/runs?limit=50&offset=50").json()
    assert len(page) == 5
    assert {row["id"] for row in page} == {str(run.id) for run in owned[:5]}


def test_review_export_is_attributed_and_owned(auth_client, other_client, user):
    from apps.results.models import Annotation

    run = AnalysisRun.objects.create(
        idempotency_key=str(uuid4()),
        created_by=user,
        input_mode="direct",
        trigger_sequence="ACGU" * 10,
    )
    candidate = Candidate.objects.create(run=run, engine_ref="cand-reviewed", gate_family="toehold")
    Annotation.objects.create(
        candidate=candidate, author=user, text="Retain for research", decision_tag="SHORTLISTED"
    )
    url = f"/api/runs/{run.id}/review.json"
    response = auth_client.get(url)
    assert response.status_code == 200
    note = response.json()["annotations"][0]
    assert note["author"] == user.username
    assert note["engine_ref"] == "cand-reviewed"
    assert note["decision_tag"] == "SHORTLISTED"
    assert other_client.get(url).status_code == 404


def test_top_n_selects_global_ranks_before_filter_sort_and_pagination(auth_client, run):
    Candidate.objects.bulk_create(
        [
            Candidate(
                run=run,
                engine_ref=f"cand-{index:05d}",
                rank=index,
                overall_score=1 - index / 10,
                gate_family="toehold",
                design={"logic_graph": {"output": "gfp" if index <= 2 else "other"}},
            )
            for index in range(1, 6)
        ]
        + [
            Candidate(
                run=run,
                engine_ref="rejected",
                is_rejected=True,
                rejection_reason="Diagnostic",
                gate_family="toehold",
            )
        ]
    )
    url = f"/api/runs/{run.id}/candidates"
    page = auth_client.get(f"{url}?top_n=3&limit=1&offset=1&sort=-rank").json()
    assert page["count"] == 3
    assert [c["rank"] for c in page["items"]] == [2]
    selected = auth_client.get(f"{url}?top_n=3&sort=overall_score&include_rejected=true").json()
    assert [c["rank"] for c in selected["items"]] == [3, 2, 1]
    filtered = auth_client.get(f"{url}?top_n=3&output=other").json()
    assert filtered["count"] == 1
    assert filtered["items"][0]["rank"] == 3
    assert auth_client.get(f"{url}?include_rejected=true").json()["count"] == 6
    assert Candidate.objects.filter(run=run).count() == 6


@pytest.mark.parametrize("value", [0, -1, 1001, "true", "1.5"])
def test_paginated_candidates_reject_invalid_top_n(auth_client, run, value):
    response = auth_client.get(f"/api/runs/{run.id}/candidates?top_n={value}")
    assert response.status_code == 422, response.content
