"""POST /api/design and its two GETs — the one-call fast path (docs/public-api.md §8-§9).

Session and key auth both reach this endpoint; the design-scope and concurrency-ceiling
tests live in tests/api/test_scopes_and_quotas.py, not here.
"""

import json

import pytest

from apps.accounts.services import issue_api_key

TRIGGER = "AUGGCUAAGCUUAACGGAUCCAUGGCUAAGCUUAAC"


@pytest.fixture
def design_key(user):
    _key, secret = issue_api_key(owner=user, label="test-client")
    return secret


def _post(client, secret, body, **query):
    qs = "&".join(f"{k}={v}" for k, v in query.items())
    url = "/api/design" + (f"?{qs}" if qs else "")
    return client.post(
        url, data=json.dumps(body), content_type="application/json", HTTP_X_API_KEY=secret
    )


# --- The fast path: direct mode ----------------------------------------------------


def test_direct_trigger_submits_and_queues(client, design_key):
    response = _post(client, design_key, {"trigger_sequence": TRIGGER, "organism": "ecoli"})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "QUEUED"
    assert body["resolved"]["input_mode"] == "direct"


def test_resolved_echoes_every_default(client, design_key):
    body = _post(client, design_key, {"trigger_sequence": TRIGGER, "organism": "ecoli"}).json()

    resolved = body["resolved"]
    assert resolved["scoring_profile"] == "default"
    assert "toehold" in resolved["gate_families"]
    assert resolved.get("seed") is None
    assert resolved["payload"] == {"outputs": ["gfp"], "optimize_codons": False}


def test_response_carries_poll_and_results_urls(client, design_key):
    body = _post(client, design_key, {"trigger_sequence": TRIGGER, "organism": "ecoli"}).json()

    assert body["poll_url"] == f"/api/design/{body['job_id']}"
    assert body["results_url"] == f"/api/design/{body['job_id']}/results"
    assert body["web_url"] == f"/runs/{body['job_id']}"


def test_estimate_is_present_and_rough(client, design_key):
    body = _post(client, design_key, {"trigger_sequence": TRIGGER, "organism": "ecoli"}).json()

    assert body["estimate"]["designs"] > 0
    assert body["estimate"]["confidence"] in ("rough", "very rough")
    assert body["estimate"].get("seconds") is None
    assert body["estimate"]["runtime_calibrated"] is False
    assert body["estimate"]["designs"] <= body["estimate"]["candidate_upper_bound"]


# --- Input resolution --------------------------------------------------------------


def test_dataset_id_mode_uses_the_existing_dataset(client, design_key, dataset):
    response = _post(client, design_key, {"dataset_id": str(dataset.id), "organism": "ecoli"})

    assert response.status_code == 202
    assert response.json()["resolved"]["input_mode"] == "de"


def test_inline_dge_csv_creates_a_dataset(client, design_key, user):
    from apps.datasets.models import Dataset

    csv = "gene_id,log2fc,padj\nlacZ,3.1,0.001\nkatG,2.4,0.002\n"
    response = _post(client, design_key, {"dge_csv": csv, "organism": "ecoli"})

    assert response.status_code == 202
    assert Dataset.objects.filter(uploaded_by=user, name="dge.csv (inline)").exists()


def test_zero_inputs_is_a_422_naming_the_conflict(client, design_key):
    response = _post(client, design_key, {"organism": "ecoli"})

    assert response.status_code == 422
    assert response.json()["error"]["detail"]["provided"] == []


def test_two_inputs_is_a_422_naming_the_conflict(client, design_key, dataset):
    response = _post(
        client,
        design_key,
        {"trigger_sequence": TRIGGER, "dataset_id": str(dataset.id), "organism": "ecoli"},
    )

    assert response.status_code == 422
    assert set(response.json()["error"]["detail"]["provided"]) == {
        "trigger_sequence",
        "dataset_id",
    }


# --- gate families -------------------------------------------------------------------


def test_unknown_gate_family_is_422(client, design_key):
    response = _post(
        client,
        design_key,
        {"trigger_sequence": TRIGGER, "gate_families": ["not-a-real-family"], "organism": "ecoli"},
    )
    assert response.status_code == 422


def test_exclude_gate_families_removes_from_the_available_set(client, design_key):
    response = _post(
        client,
        design_key,
        {"trigger_sequence": TRIGGER, "exclude_gate_families": ["toehold"], "organism": "ecoli"},
    )
    assert response.status_code == 202
    assert "toehold" not in response.json()["resolved"]["gate_families"]


def test_excluding_every_family_is_422(client, design_key):
    from engine.client import LocalEngine

    all_families = LocalEngine().capabilities().available_families
    response = _post(
        client,
        design_key,
        {
            "trigger_sequence": TRIGGER,
            "exclude_gate_families": all_families,
            "organism": "ecoli",
        },
    )
    assert response.status_code == 422


# --- strict mode (§9.2) --------------------------------------------------------------


def test_strict_defaults_true_and_catches_constraint_typos(client, design_key):
    response = _post(
        client,
        design_key,
        {"trigger_sequence": TRIGGER, "organism": "ecoli", "constraints": {"max_trigger": 2}},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "unknown_parameter"
    assert body["error"]["detail"]["did_you_mean"] == "max_triggers"


def test_strict_false_cannot_accept_an_unimplemented_constraint(client, design_key):
    response = _post(
        client,
        design_key,
        {
            "trigger_sequence": TRIGGER,
            "organism": "ecoli",
            "constraints": {"max_trigger": 2},
            "strict": False,
        },
    )
    assert response.status_code == 422


def test_strict_catches_an_unknown_scoring_metric_name(client, design_key):
    response = _post(
        client,
        design_key,
        {
            "trigger_sequence": TRIGGER,
            "organism": "ecoli",
            "scoring": {"weights": {"leakage": 4.0}},
        },
    )
    assert response.status_code == 422
    assert "leakage" in response.json()["error"]["message"]


def test_a_valid_scoring_override_is_accepted(client, design_key):
    response = _post(
        client,
        design_key,
        {
            "trigger_sequence": TRIGGER,
            "organism": "ecoli",
            "scoring": {"weights": {"predicted_leakage": 4.0, "gc_content": 0.0}},
        },
    )
    assert response.status_code == 202


def test_a_scoring_override_of_all_zero_weights_is_a_422(client, design_key):
    from engine.client import LocalEngine

    weights = {metric.name: 0.0 for metric in LocalEngine().capabilities().metrics}
    response = _post(
        client,
        design_key,
        {"trigger_sequence": TRIGGER, "organism": "ecoli", "scoring": {"weights": weights}},
    )
    assert response.status_code == 422


def test_resolved_scoring_profile_is_the_custom_label_not_the_base_name(client, design_key):
    body = _post(
        client,
        design_key,
        {
            "trigger_sequence": TRIGGER,
            "organism": "ecoli",
            "scoring": {"weights": {"predicted_leakage": 4.0}},
        },
    ).json()

    assert body["resolved"]["scoring_profile"].startswith("custom-")


def test_resolved_scoring_profile_stays_the_base_name_without_overrides(client, design_key):
    body = _post(client, design_key, {"trigger_sequence": TRIGGER, "organism": "ecoli"}).json()
    assert body["resolved"]["scoring_profile"] == "default"


# --- dry_run (§9.3) -------------------------------------------------------------------


def test_dry_run_returns_an_estimate_and_creates_nothing(client, design_key):
    from apps.analyses.models import AnalysisRun

    before_runs = AnalysisRun.objects.count()

    response = _post(
        client, design_key, {"trigger_sequence": TRIGGER, "organism": "ecoli"}, dry_run="true"
    )

    assert response.status_code == 200
    body = response.json()
    assert body.get("job_id") is None
    assert body["estimate"]["designs"] > 0
    assert body["budget_ok"] is True
    assert AnalysisRun.objects.count() == before_runs


def test_dry_run_bounds_de_mode_from_the_dataset_row_count(client, design_key, dataset):
    response = _post(
        client,
        design_key,
        {"dataset_id": str(dataset.id), "organism": "ecoli"},
        dry_run="true",
    )

    assert response.status_code == 200
    assert response.json()["estimate"]["confidence"] == "rough"


# --- wait= (§8) -------------------------------------------------------------------


def test_wait_returns_202_on_timeout(client, design_key, dataset):
    response = _post(
        client,
        design_key,
        {"dataset_id": str(dataset.id), "organism": "ecoli"},
        wait="0.05",
    )

    assert response.status_code == 202


def test_wait_cannot_reuse_key_for_different_configuration(client, design_key, completed_run):
    response = _post(
        client,
        design_key,
        {
            "dataset_id": str(completed_run.dataset_id),
            "organism": "ecoli",
            "idempotency_key": completed_run.idempotency_key,
        },
        wait="5",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


# --- GET /api/design/{id} and /results ----------------------------------------------


def test_get_design_status_is_a_thin_alias(client, design_key, run):
    response = client.get(f"/api/design/{run.id}", HTTP_X_API_KEY=design_key)

    assert response.status_code == 200
    assert response.json()["status"] == run.status


def test_get_design_status_of_someone_elses_run_is_404(client, other_user, run):
    _key, secret = issue_api_key(owner=other_user, label="not-yours")
    response = client.get(f"/api/design/{run.id}", HTTP_X_API_KEY=secret)
    assert response.status_code == 404


def test_get_design_results_ranks_and_caps_by_top_n(client, design_key, completed_run):
    response = client.get(
        f"/api/design/{completed_run.id}/results?top_n=3", HTTP_X_API_KEY=design_key
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["candidates"]) <= 3
    ranks = [c["rank"] for c in body["candidates"]]
    assert ranks == sorted(ranks)


def test_get_design_results_excludes_rejected_by_default(client, design_key, completed_run):
    body = client.get(
        f"/api/design/{completed_run.id}/results?top_n=100", HTTP_X_API_KEY=design_key
    ).json()

    assert all(not c["is_rejected"] for c in body["candidates"])


def test_get_design_results_include_rejected(client, design_key, completed_run):
    from apps.results.models import Candidate

    total = Candidate.objects.filter(run=completed_run).count()

    body = client.get(
        f"/api/design/{completed_run.id}/results?top_n=100&include_rejected=true",
        HTTP_X_API_KEY=design_key,
    ).json()

    assert len(body["candidates"]) == min(total, 100)


def test_get_design_results_csv_delegates_to_the_existing_export(client, design_key, completed_run):
    response = client.get(
        f"/api/design/{completed_run.id}/results?format=csv", HTTP_X_API_KEY=design_key
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"


def test_get_design_results_carries_metrics(client, design_key, completed_run):
    body = client.get(
        f"/api/design/{completed_run.id}/results?top_n=1", HTTP_X_API_KEY=design_key
    ).json()

    assert body["candidates"][0]["metrics"], "decomposition should be embedded"


@pytest.mark.parametrize("dry_run", ["true", "false"])
def test_estimate_respects_design_budget_and_output_cross_product(client, design_key, dry_run):
    response = _post(
        client,
        design_key,
        {
            "trigger_sequence": TRIGGER,
            "organism": "ecoli",
            "budget": {"max_designs": 1},
            "payload": {"outputs": ["gfp", "other"], "custom_sequence": "ATGGCTGCTTAA"},
        },
        dry_run=dry_run,
    )
    assert response.status_code in (200, 202), response.content
    estimate = response.json()["estimate"]
    assert estimate["designs"] == estimate["candidate_upper_bound"] == 2
    assert estimate.get("seconds") is None
    assert estimate["runtime_calibrated"] is False


@pytest.mark.parametrize("dry_run", ["true", "false"])
def test_top_n_does_not_reduce_evaluation_budget_or_estimate(client, design_key, dry_run):
    from apps.analyses.models import AnalysisRun

    response = _post(
        client,
        design_key,
        {
            "trigger_sequence": TRIGGER,
            "organism": "ecoli",
            "top_n": 1,
            "budget": {"max_designs": 40},
            "payload": {"outputs": ["gfp", "other"], "custom_sequence": "ATGGCTGCTTAA"},
        },
        dry_run=dry_run,
    )
    assert response.status_code in (200, 202), response.content
    body = response.json()
    assert body["estimate"]["candidate_upper_bound"] == 80
    assert body["estimate"]["designs"] > 1
    assert body["resolved"]["budget"]["max_designs"] == 40
    if dry_run == "true":
        assert not AnalysisRun.objects.exists()
    else:
        assert AnalysisRun.objects.get(pk=body["job_id"]).params_snapshot["budget"] == {
            "max_designs": 40,
        }


def test_async_results_url_preserves_top_n_without_pruning_stored_candidates(client, design_key):
    import csv
    import io
    from urllib.parse import parse_qs, urlsplit

    from apps.analyses.models import AnalysisRun, RunStatus
    from apps.results.models import Candidate

    response = _post(
        client,
        design_key,
        {
            "trigger_sequence": TRIGGER,
            "organism": "ecoli",
            "top_n": 2,
            "budget": {"max_designs": 40},
        },
    )
    assert response.status_code == 202, response.content
    body = response.json()
    assert parse_qs(urlsplit(body["results_url"]).query)["top_n"] == ["2"]
    run = AnalysisRun.objects.get(pk=body["job_id"])
    run.status = RunStatus.COMPLETED
    run.save(update_fields=["status"])
    # Generation order differs from score order, and a rejected row comes first.
    Candidate.objects.bulk_create(
        [
            Candidate(
                run=run,
                engine_ref="cand-000000",
                is_rejected=True,
                rejection_reason="Hard-filter diagnostic",
                gate_family="toehold",
            ),
            *[
                Candidate(
                    run=run,
                    engine_ref=f"cand-{index:06d}",
                    rank=31 - index,
                    overall_score=index / 31,
                    gate_family="toehold",
                )
                for index in range(1, 31)
            ],
        ]
    )
    result = client.get(body["results_url"], HTTP_X_API_KEY=design_key)
    assert result.status_code == 200, result.content
    assert [c["engine_ref"] for c in result.json()["candidates"]] == [
        "cand-000030",
        "cand-000029",
    ]
    assert Candidate.objects.filter(run=run).count() == 31
    csv_response = client.get(
        f"/api/design/{run.id}/results?format=csv&top_n=2",
        HTTP_X_API_KEY=design_key,
    )
    rows = list(csv.DictReader(io.StringIO(csv_response.content.decode())))
    assert len(rows) == 31
    all_results = client.get(
        f"/api/design/{run.id}/results?top_n=100&include_rejected=true",
        HTTP_X_API_KEY=design_key,
    ).json()
    assert len(all_results["candidates"]) == 31
    assert all_results["candidates"][-1]["is_rejected"] is True


def test_async_results_url_preserves_nondefault_output_options(client, design_key):
    from urllib.parse import parse_qs, urlsplit

    body = _post(
        client,
        design_key,
        {
            "trigger_sequence": TRIGGER,
            "organism": "ecoli",
            "top_n": 7,
            "include_rejected": True,
            "include_metrics": False,
            "include_artifacts": ["design_table", "safety_audit"],
        },
    ).json()
    query = parse_qs(urlsplit(body["results_url"]).query)
    assert query == {
        "top_n": ["7"],
        "include_rejected": ["true"],
        "include_metrics": ["false"],
        "include_artifacts": ["design_table,safety_audit"],
    }


@pytest.mark.parametrize("value", [0, -1, 1001, True, False, 1.5, "2", None])
@pytest.mark.parametrize("dry_run", ["true", "false"])
def test_top_n_requires_a_bounded_integer_before_submission(client, design_key, value, dry_run):
    from apps.analyses.models import AnalysisRun

    response = _post(
        client,
        design_key,
        {
            "trigger_sequence": TRIGGER,
            "organism": "ecoli",
            "top_n": value,
        },
        dry_run=dry_run,
    )
    assert response.status_code == 422, response.content
    assert not AnalysisRun.objects.exists()


@pytest.mark.parametrize("value", [0, -1, 1001, "true", "1.5"])
def test_design_results_reject_invalid_top_n(auth_client, run, value):
    response = auth_client.get(f"/api/design/{run.id}/results?top_n={value}")
    assert response.status_code == 422, response.content
