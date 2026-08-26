"""Django admin is the v1 back-office (docs/architecture.md §13 Step 2).

Two things are being checked: every model is genuinely manageable, and admin cannot be
used to sidestep the run state machine (rule 5) or edit a submitted run (rule 7).
"""

import pytest

from apps.results.services import import_job_result

CHANGELISTS = [
    "/admin/",
    "/admin/accounts/user/",
    "/admin/projects/project/",
    "/admin/datasets/dataset/",
    "/admin/analyses/analysisrun/",
    "/admin/results/candidate/",
    "/admin/results/candidatemetric/",
    "/admin/results/artifact/",
    "/admin/results/annotation/",
]


@pytest.fixture
def admin_client_with_data(client, staff_user, run, job_result):
    result, output_dir = job_result
    import_job_result(run, result, output_dir)
    client.force_login(staff_user)
    return client


@pytest.mark.parametrize("url", CHANGELISTS)
def test_every_changelist_renders(admin_client_with_data, url):
    assert admin_client_with_data.get(url).status_code == 200


def test_run_detail_page_renders(admin_client_with_data, run):
    response = admin_client_with_data.get(f"/admin/analyses/analysisrun/{run.id}/change/")
    assert response.status_code == 200


def test_candidate_detail_renders_with_its_inlines(admin_client_with_data, run):
    candidate = run.candidates.filter(is_rejected=False).first()
    response = admin_client_with_data.get(f"/admin/results/candidate/{candidate.id}/change/")
    body = response.content.decode()

    assert response.status_code == 200
    assert "state_separation" in body, "metric inline should be visible"


def test_run_status_is_not_editable_in_admin(admin_client_with_data, run):
    """Rule 5: transitions happen only in apps/analyses/services.py."""
    body = admin_client_with_data.get(
        f"/admin/analyses/analysisrun/{run.id}/change/"
    ).content.decode()

    assert 'name="status"' not in body
    assert 'name="params_snapshot"' not in body, "a submitted run is immutable (rule 7)"


def test_runs_cannot_be_created_by_hand(admin_client_with_data):
    assert admin_client_with_data.get("/admin/analyses/analysisrun/add/").status_code == 403


def test_candidates_cannot_be_created_by_hand(admin_client_with_data):
    """Engine output is a record of what was computed, not something staff author."""
    assert admin_client_with_data.get("/admin/results/candidate/add/").status_code == 403


def test_annotations_remain_editable(admin_client_with_data):
    """Product-owned decisions, unlike engine output, are meant to be edited."""
    assert admin_client_with_data.get("/admin/results/annotation/add/").status_code == 200


def test_run_changelist_filters_by_status(admin_client_with_data):
    response = admin_client_with_data.get("/admin/analyses/analysisrun/?status__exact=QUEUED")
    assert response.status_code == 200


def test_admin_requires_login(client):
    response = client.get("/admin/projects/project/")
    assert response.status_code == 302
    assert "/login/" in response["Location"]
