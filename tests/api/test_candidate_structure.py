"""Candidate-specific read-only RNA geometry with the existing ownership boundary."""

import copy
from uuid import uuid4

import pytest

from apps.accounts.models import ApiKeyScope
from apps.accounts.services import issue_api_key
from apps.results.models import Candidate
from engine.gates.tools import folding
from engine.gates.tools.folding import FoldEngine


@pytest.fixture
def stored_candidate(run):
    # Already persisted data only; no compiler run or scientific recomputation.
    return Candidate.objects.create(
        run=run,
        engine_ref="stored-layout-fixture",
        gate_family="toehold",
        logic_type="YES",
        design={
            "switch_sequence": "GGGAAACCC",
            "structure": "(((...)))",
            "structure_kind": "intended_target",
            "architecture": {"unchanged": True},
        },
    )


@pytest.fixture(autouse=True)
def forbid_scientific_computation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Reading structure must not compute a scientific result")

    monkeypatch.setattr(FoldEngine, "__init__", forbidden)
    for name in ("fold_compound", "fold", "cofold"):
        monkeypatch.setattr(folding.RNA, name, forbidden)


def test_structure_is_authenticated_read_only_geometry(auth_client, stored_candidate):
    candidate_before = Candidate.objects.values().get(pk=stored_candidate.pk)
    run_before = type(stored_candidate.run).objects.values().get(pk=stored_candidate.run_id)
    response = auth_client.get(f"/api/candidates/{stored_candidate.id}/structure")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    assert body["reason"] is None
    assert body["sequence"] == stored_candidate.design["switch_sequence"]
    assert body["structure"] == stored_candidate.design["structure"]
    assert body["structure_kind"] == "intended_target"
    assert len(body["bases"]) == 9
    assert body["links"] == [
        {"source": 0, "target": 8},
        {"source": 1, "target": 7},
        {"source": 2, "target": 6},
    ]
    assert body["renderer"] == "cernal-rnaviz"
    assert body["renderer_version"] == "aa112e17a76941233987bb4287c2c66511c40d13"
    assert Candidate.objects.values().get(pk=stored_candidate.pk) == candidate_before
    assert type(stored_candidate.run).objects.values().get(pk=stored_candidate.run_id) == run_before


def test_historical_candidate_does_not_gain_invented_provenance(auth_client, stored_candidate):
    stored_candidate.design.pop("structure_kind")
    stored_candidate.save(update_fields=["design"])
    body = auth_client.get(f"/api/candidates/{stored_candidate.id}/structure").json()
    assert body["status"] == "available"
    assert body["structure_kind"] is None
    stored_candidate.refresh_from_db()
    assert "structure_kind" not in stored_candidate.design


def test_query_parameters_cannot_submit_a_different_sequence(auth_client, stored_candidate):
    response = auth_client.get(
        f"/api/candidates/{stored_candidate.id}/structure?sequence=UU&structure=.."
    )
    assert response.status_code == 200
    assert response.json()["sequence"] == "GGGAAACCC"
    assert response.json()["structure"] == "(((...)))"


def test_multi_gate_candidate_uses_stored_primary_switch(auth_client, stored_candidate):
    stored_candidate.design["component_switches"] = [
        {"switch_sequence": "AAAA", "structure": "...."},
        {"switch_sequence": "UU", "structure": ".."},
    ]
    stored_candidate.design["structure_kind"] = "legacy_source_label"
    stored_candidate.save(update_fields=["design"])
    body = auth_client.get(f"/api/candidates/{stored_candidate.id}/structure").json()
    assert body["sequence"] == "GGGAAACCC"
    assert body["structure"] == "(((...)))"
    assert body["structure_kind"] == "legacy_source_label"


@pytest.mark.parametrize(
    "design,status",
    [
        ({}, "unavailable"),
        ({"switch_sequence": "A"}, "unavailable"),
        ({"switch_sequence": "A", "structure": ""}, "unavailable"),
        ({"switch_sequence": ["A"], "structure": "."}, "invalid"),
        ({"switch_sequence": "AT", "structure": ".."}, "invalid"),
        ({"switch_sequence": "au", "structure": ".."}, "invalid"),
        ({"switch_sequence": "AA", "structure": ")("}, "invalid"),
        ({"switch_sequence": "AA", "structure": "."}, "invalid"),
        ({"switch_sequence": "A&U", "structure": ".&."}, "invalid"),
        ({"switch_sequence": "A" * 2001, "structure": "." * 2001}, "unavailable"),
        ([], "invalid"),
    ],
)
def test_unusable_stored_data_has_safe_status_without_mutation(
    auth_client, stored_candidate, design, status
):
    before = copy.deepcopy(design)
    stored_candidate.design = design
    stored_candidate.save(update_fields=["design"])
    response = auth_client.get(f"/api/candidates/{stored_candidate.id}/structure")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == status
    assert body["reason"]
    assert body["bases"] == body["links"] == []
    stored_candidate.refresh_from_db()
    assert stored_candidate.design == before


def test_native_error_is_safe_for_api_consumer(auth_client, stored_candidate, monkeypatch):
    def failed(*args):
        raise RuntimeError("secret filesystem details")

    monkeypatch.setattr(folding.RNA, "naview_xy_coordinates", failed)
    response = auth_client.get(f"/api/candidates/{stored_candidate.id}/structure")
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert "secret" not in response.content.decode()


def test_no_authentication_is_401(client, stored_candidate):
    assert client.get(f"/api/candidates/{stored_candidate.id}/structure").status_code == 401


def test_other_owner_and_missing_candidate_are_404(other_client, stored_candidate, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unauthorised candidate data reached the engine")

    monkeypatch.setattr("api.routers.results.layout_stored_structure", forbidden)
    assert other_client.get(f"/api/candidates/{stored_candidate.id}/structure").status_code == 404
    assert other_client.get(f"/api/candidates/{uuid4()}/structure").status_code == 404


def test_read_api_key_has_same_access_as_candidate_get(client, user, stored_candidate):
    _, secret = issue_api_key(owner=user, label="layout reader", scopes=(ApiKeyScope.READ,))
    headers = {"HTTP_X_API_KEY": secret}
    assert client.get(f"/api/candidates/{stored_candidate.id}", **headers).status_code == 200
    response = client.get(f"/api/candidates/{stored_candidate.id}/structure", **headers)
    assert response.status_code == 200
    assert response.json()["status"] == "available"


def test_other_owners_api_key_cannot_read_structure(client, other_user, stored_candidate):
    _, secret = issue_api_key(owner=other_user, label="another reader")
    response = client.get(f"/api/candidates/{stored_candidate.id}/structure", HTTP_X_API_KEY=secret)
    assert response.status_code == 404


def test_staff_access_matches_candidate_detail(client, staff_user, stored_candidate):
    client.force_login(staff_user)
    assert client.get(f"/api/candidates/{stored_candidate.id}/structure").status_code == 200


def test_structure_endpoint_is_read_only(auth_client, stored_candidate):
    response = auth_client.post(f"/api/candidates/{stored_candidate.id}/structure")
    assert response.status_code == 405
