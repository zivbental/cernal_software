"""Candidates, artifacts, exports and annotations."""

import csv
import io
import json


def test_candidates_are_ranked_best_first(auth_client, completed_run):
    body = auth_client.get(f"/api/runs/{completed_run.id}/candidates?limit=100").json()
    ranks = [c["rank"] for c in body["items"]]

    assert ranks == sorted(ranks)
    assert ranks[0] == 1


def test_rejected_candidates_are_hidden_by_default_but_available(auth_client, completed_run):
    """Rule 8: they are kept, not deleted — the researcher chooses whether to look."""
    default = auth_client.get(f"/api/runs/{completed_run.id}/candidates?limit=100").json()
    with_rejected = auth_client.get(
        f"/api/runs/{completed_run.id}/candidates?limit=100&include_rejected=true"
    ).json()

    assert with_rejected["count"] > default["count"]
    rejected = [c for c in with_rejected["items"] if c["is_rejected"]]
    assert rejected
    assert all(c["rejection_reason"] for c in rejected)


def test_unranked_candidates_never_lead_the_list(auth_client, completed_run):
    body = auth_client.get(
        f"/api/runs/{completed_run.id}/candidates?limit=100&include_rejected=true"
    ).json()

    assert body["items"][0]["rank"] is not None


def test_candidates_can_be_sorted_by_score_descending(auth_client, completed_run):
    body = auth_client.get(
        f"/api/runs/{completed_run.id}/candidates?limit=100&sort=-overall_score"
    ).json()
    scores = [c["overall_score"] for c in body["items"]]

    assert scores == sorted(scores, reverse=True)


def test_an_unsortable_field_is_refused_with_the_allowed_list(auth_client, completed_run):
    """An open sort parameter invites schema probing and expensive queries."""
    response = auth_client.get(f"/api/runs/{completed_run.id}/candidates?sort=params_snapshot")

    assert response.status_code == 422
    assert "rank" in response.json()["error"]["detail"]["sortable"]


def test_candidates_can_be_filtered_by_gate_family(auth_client, completed_run):
    body = auth_client.get(
        f"/api/runs/{completed_run.id}/candidates?limit=100&gate_family=toehold"
    ).json()

    assert body["count"] > 0
    assert all(c["gate_family"] == "toehold" for c in body["items"])


def test_candidates_paginate(auth_client, completed_run):
    body = auth_client.get(f"/api/runs/{completed_run.id}/candidates?limit=3").json()
    assert len(body["items"]) == 3


def test_candidate_detail_carries_the_full_decomposition(auth_client, completed_run):
    """Design map 12: report the decomposition, not a single opaque score."""
    listed = auth_client.get(f"/api/runs/{completed_run.id}/candidates").json()["items"][0]
    body = auth_client.get(f"/api/candidates/{listed['id']}").json()

    assert body["design"]["switch_sequence"]
    assert body["triggers"]["features"]
    names = {m["name"] for m in body["metrics"]}
    assert {"state_separation", "predicted_leakage"} <= names
    assert all(m["direction"] in ("HIGHER_BETTER", "LOWER_BETTER") for m in body["metrics"])


def test_another_users_candidates_are_invisible(other_client, completed_run):
    assert other_client.get(f"/api/runs/{completed_run.id}/candidates").status_code == 404


# --- Artifacts --------------------------------------------------------------------


def test_artifacts_are_listed_with_an_api_download_url(auth_client, completed_run):
    body = auth_client.get(f"/api/runs/{completed_run.id}/artifacts").json()

    assert body
    for artifact in body:
        assert artifact["download_url"].startswith("/api/artifacts/")
        assert "var/" not in json.dumps(artifact), "never expose a storage path (§7.2)"


def test_an_artifact_downloads_with_its_bytes(auth_client, completed_run):
    artifact = auth_client.get(f"/api/runs/{completed_run.id}/artifacts").json()[0]
    response = auth_client.get(artifact["download_url"])
    content = b"".join(response.streaming_content)

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    assert len(content) == artifact["size_bytes"]


def test_another_user_cannot_download_an_artifact(other_client, auth_client, completed_run):
    """Artifacts go through an authorized view, never a static handler (§7.2)."""
    artifact = auth_client.get(f"/api/runs/{completed_run.id}/artifacts").json()[0]

    assert other_client.get(artifact["download_url"]).status_code == 404


def test_downloading_needs_authentication(client, auth_client, completed_run):
    artifact = auth_client.get(f"/api/runs/{completed_run.id}/artifacts").json()[0]
    auth_client.logout()

    assert client.get(artifact["download_url"]).status_code == 401


# --- Export -----------------------------------------------------------------------


def test_csv_export_is_a_flat_candidate_by_metric_table(auth_client, completed_run):
    response = auth_client.get(f"/api/runs/{completed_run.id}/export.csv")
    rows = list(csv.reader(io.StringIO(response.content.decode())))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"

    header = rows[0]
    assert header[:3] == ["candidate", "rank", "overall_score"]
    assert "state_separation_raw" in header
    assert "state_separation_normalized" in header
    assert len(rows) - 1 == completed_run.candidates.count()


def test_csv_export_includes_rejected_candidates_and_reasons(auth_client, completed_run):
    response = auth_client.get(f"/api/runs/{completed_run.id}/export.csv")
    reader = csv.DictReader(io.StringIO(response.content.decode()))
    rejected = [row for row in reader if row["rejected"] == "yes"]

    assert rejected
    assert all(row["rejection_reason"] for row in rejected)


# --- Annotations ------------------------------------------------------------------


def test_an_annotation_can_be_added_and_listed(auth_client, completed_run):
    candidate = auth_client.get(f"/api/runs/{completed_run.id}/candidates").json()["items"][0]

    created = auth_client.post(
        f"/api/candidates/{candidate['id']}/annotations",
        data=json.dumps({"text": "Shortlist this.", "decision_tag": "SHORTLISTED"}),
        content_type="application/json",
    )
    assert created.status_code == 201
    assert created.json()["author"] == "researcher"

    listed = auth_client.get(f"/api/candidates/{candidate['id']}/annotations").json()
    assert [a["text"] for a in listed] == ["Shortlist this."]


def test_an_unknown_decision_tag_is_refused_with_the_allowed_set(auth_client, completed_run):
    candidate = auth_client.get(f"/api/runs/{completed_run.id}/candidates").json()["items"][0]

    response = auth_client.post(
        f"/api/candidates/{candidate['id']}/annotations",
        data=json.dumps({"text": "", "decision_tag": "MAYBE"}),
        content_type="application/json",
    )

    assert response.status_code == 422
    assert "PINNED" in response.json()["error"]["detail"]["allowed"]


def test_an_annotation_can_be_deleted(auth_client, completed_run):
    candidate = auth_client.get(f"/api/runs/{completed_run.id}/candidates").json()["items"][0]
    created = auth_client.post(
        f"/api/candidates/{candidate['id']}/annotations",
        data=json.dumps({"text": "temp", "decision_tag": "NONE"}),
        content_type="application/json",
    ).json()

    assert auth_client.delete(f"/api/annotations/{created['id']}").status_code == 204


def test_cannot_annotate_another_users_candidate(other_client, auth_client, completed_run):
    candidate = auth_client.get(f"/api/runs/{completed_run.id}/candidates").json()["items"][0]

    response = other_client.post(
        f"/api/candidates/{candidate['id']}/annotations",
        data=json.dumps({"text": "sneaky", "decision_tag": "NONE"}),
        content_type="application/json",
    )
    assert response.status_code == 404
