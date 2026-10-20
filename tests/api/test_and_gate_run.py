"""The two-input eukaryotic AND gate through the whole application.

Each test drives the real stack the way a user does: the capability document the UI reads, a
submission to ``POST /api/runs`` with the same parameters the wizard sends, the worker running the
real engine (ViennaRNA, no stub), the saved candidates and exports, and reopening them. Nothing
here is mocked except the screening adapter in the one test that proves sequences are released
only through the safety gate.

Two human genes (SELE and ICAM1, up-regulated) are the small reproducible example: a differential
expression table of two rows, run with a cheap sampling budget. What the run finds is a property of
the science; these tests pin its *shape* (what is saved, what is withheld, what is rejected and
why), not a number.
"""

import json

import pytest

from apps.analyses.models import AnalysisRun, RunStatus

AND_FAMILY = "eukaryotic_toehold_and"

#: The example table: two real human genes, both up-regulated, with their Ensembl identifiers.
AND_TABLE = (
    "gene_id,gene_symbol,log2fc,padj\n"
    "ENSG00000007908,SELE,3.4,0.0001\n"
    "ENSG00000090339,ICAM1,2.6,0.0004\n"
)

#: A cheap but real budget: 200 sampled structures per state, two controls, two evaluated designs.
FAST_AND_GATE = {"n_samples": 200, "screen_samples": 100, "n_controls": 2}


def _params(**overrides) -> dict:
    params = {
        "constraints": {"max_triggers": 2, "max_circuit_gates": 1},
        "and_inputs": {"gene_a": "SELE", "gene_b": "ICAM1"},
        "and_gate": dict(FAST_AND_GATE),
        "payload": {"outputs": ["gfp"]},
        "budget": {"max_designs": 2},
    }
    params.update(overrides)
    return params


def _upload(auth_client, csv_upload, content=AND_TABLE) -> str:
    response = auth_client.post("/api/datasets", data={"file": csv_upload(content)})
    assert response.status_code == 201, response.content
    assert response.json()["validation_status"] == "VALID"
    return response.json()["id"]


def _submit(auth_client, **payload):
    return auth_client.post("/api/runs", data=json.dumps(payload), content_type="application/json")


def _submit_and_run(auth_client, csv_upload, capture, *, table=AND_TABLE, **overrides) -> str:
    """Submit the wizard's payload for the AND gate and let the worker execute it."""
    from apps.analyses.tasks import run_analysis

    dataset_id = _upload(auth_client, csv_upload, table)
    payload = {
        "input_mode": "de",
        "dataset_id": dataset_id,
        "organism": "human",
        "gate_families": [AND_FAMILY],
        "seed": 7,
        "params": _params(),
    }
    payload.update(overrides)
    with capture():
        response = _submit(auth_client, **payload)
    assert response.status_code == 202, response.content
    run_id = response.json()["id"]
    run_analysis(run_id)
    return run_id


# --- What the UI is told it can do -------------------------------------------------------------


def test_the_capability_document_advertises_the_and_gate_exactly_where_it_runs(auth_client):
    version = auth_client.get("/api/version").json()

    family = next(f for f in version["gate_families"] if f["name"] == AND_FAMILY)
    assert family["available"] is True
    assert version["family_hosts"][AND_FAMILY] == ["human", "yeast"]
    assert version["family_inputs"][AND_FAMILY] == 2
    assert version["family_input_modes"][AND_FAMILY] == ["de"]
    assert version["limits"]["max_gate_inputs"] == 2
    # The single-input default is unchanged, and the unbuilt AND chemistries stay unadvertised.
    assert version["limits"]["max_triggers"] == 1
    assert version["family_inputs"]["toehold"] == 1
    assert "ecoli" not in version["family_hosts"][AND_FAMILY]
    assert not {"toehold_and", "prokaryotic_toehold_and"} & set(version["family_inputs"])


def test_naming_no_family_never_selects_the_and_gate(auth_client):
    """ "Every available family" must not pull in a gate that needs two genes."""
    response = auth_client.post(
        "/api/design?dry_run=true",
        data=json.dumps(
            {
                "trigger_sequence": "AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA",
                "organism": "human",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert AND_FAMILY not in response.json()["resolved"]["gate_families"]


# --- Submission, execution, saved results, reopening and export ---------------------------------


def test_an_and_run_goes_from_submission_to_saved_results_and_exports(
    auth_client, csv_upload, media_root, django_capture_on_commit_callbacks
):
    run_id = _submit_and_run(auth_client, csv_upload, django_capture_on_commit_callbacks)

    # The worker finished it, and the configuration the engine ran is the one that was saved.
    status = auth_client.get(f"/api/runs/{run_id}").json()
    assert status["status"] == RunStatus.COMPLETED
    run = AnalysisRun.objects.get(pk=run_id)
    assert run.gate_families == [AND_FAMILY]
    assert run.params_snapshot["and_inputs"] == {"gene_a": "SELE", "gene_b": "ICAM1"}
    assert run.params_snapshot["constraints"]["max_triggers"] == 2
    assert run.params_snapshot["folding"]["salt_molar"] == 0.1  # the AND default, recorded

    # Reopening the run later, in a new request, returns the same saved candidates.
    listing = auth_client.get(f"/api/runs/{run_id}/candidates?include_rejected=true").json()
    assert listing["count"] > 0
    first = next(c for c in listing["items"] if not c["is_rejected"])
    assert first["gate_family"] == AND_FAMILY
    assert first["logic_type"] == "AND"
    detail = auth_client.get(f"/api/candidates/{first['id']}").json()
    assert auth_client.get(f"/api/candidates/{first['id']}").json() == detail

    # Both inputs are saved with the candidate.
    genes = [feature["gene_symbol"] for feature in detail["triggers"]["features"]]
    assert len(genes) == 2 and set(genes) <= {"SELE", "ICAM1"}
    assert detail["design"]["logic_graph"]["caption"].startswith("IF ")
    assert " AND " in detail["design"]["logic_graph"]["caption"]

    # ON/OFF diagnostics and the sampler checks are saved and visible, state by state.
    info = detail["design"]["and_gate"]
    assert set(info["states"]) == {"alone", "+A", "+B", "+A+B"}
    assert all(isinstance(state["verified"], bool) for state in info["states"].values())
    assert 0 <= info["on_pct"] <= 100 and 0 <= info["off_pct"] <= 100
    assert info["off_source"] in {"alone", "+A", "+B", "control"}
    assert info["controls"]["found"] <= info["controls"]["requested"] == 2
    assert info["tied_group"] in (True, False)  # the noise check ran, so it is determined
    assert any("experimentally validated" in warning for warning in status["warnings"])

    # The scored metrics are the profile's own names, raw, with an unmeasured value kept as null.
    metrics = {m["name"]: m for m in detail["metrics"]}
    assert metrics["predicted_leakage"]["raw_value"] == pytest.approx(info["off_pct"] / 100)
    assert metrics["circuit_complexity"]["raw_value"] == 3.0
    assert metrics["orthogonality"]["raw_value"] is None  # not measurable here, never 0.0

    # The sequence-release check is untouched: with no screening adapter the sequences are held,
    # while the sequence-free diagnostics above are still disclosed.
    assert detail["design"]["switch_sequence"] == ""
    assert detail["design"]["sequence_release"]["release_allowed"] is False

    # Exports: the summary table carries the AND columns, and the manifest the provenance.
    export = auth_client.get(f"/api/runs/{run_id}/export.csv")
    assert export.status_code == 200
    header, *rows = export.content.decode().strip().splitlines()
    assert "and_on_pct" in header and "and_tied_group" in header
    assert any(AND_FAMILY in row for row in rows)

    # The folding model that produced the numbers is saved with the candidate and disclosed with
    # it: temperature, the AND default salt, and the one override sampling needs.
    folding = detail["design"]["folding_model"]
    assert folding["configuration"]["salt_molar"] == 0.1
    assert folding["configuration"]["temperature_celsius"] == 37.0
    assert folding["sampling_model_override"] == {"uniq_ML": 1}

    # Sequence files are normal downloadable run outputs even when optional screening
    # is unavailable. The manifest keeps its separate legacy release rule.
    artifacts = auth_client.get(f"/api/runs/{run_id}/artifacts").json()
    manifest = next(a for a in artifacts if a["kind"] == "run_manifest")
    assert auth_client.get(f"/api/artifacts/{manifest['id']}/download").status_code == 409
    exports = [
        artifact
        for artifact in artifacts
        if artifact["kind"] in ("sequence_fasta", "plasmid_fasta", "genbank")
    ]
    assert {artifact["kind"] for artifact in exports} == {
        "sequence_fasta",
        "plasmid_fasta",
        "genbank",
    }
    assert all(artifact["download_available"] for artifact in exports)


def test_sequences_of_an_and_candidate_are_released_only_through_the_screening_gate(
    auth_client, csv_upload, media_root, screening_released, django_capture_on_commit_callbacks
):
    run_id = _submit_and_run(auth_client, csv_upload, django_capture_on_commit_callbacks)

    listing = auth_client.get(f"/api/runs/{run_id}/candidates").json()
    detail = auth_client.get(f"/api/candidates/{listing['items'][0]['id']}").json()
    assert detail["design"]["sequence_release"]["release_allowed"] is True
    sequence = detail["design"]["switch_sequence"]
    assert len(sequence) > 100 and set(sequence) <= set("ACGU")
    # One fused construct, one start codon: the payload's.
    assert sequence.count("AUG") == 1
    artifacts = auth_client.get(f"/api/runs/{run_id}/artifacts").json()
    assert {"sequence_fasta", "genbank"} <= {a["kind"] for a in artifacts}

    # Released, the manifest downloads and carries the run's AND provenance.
    manifest = next(a for a in artifacts if a["kind"] == "run_manifest")
    download = auth_client.get(f"/api/artifacts/{manifest['id']}/download")
    body = json.loads(b"".join(download.streaming_content))
    provenance = body["scientific_provenance"]
    assert provenance["and_gate"]["settings"]["n_samples"] == 200
    assert provenance["and_gate"]["sampler_checks"]["states_checked"] >= 4
    assert provenance["and_gate"]["noise_p95_pp"] is not None
    assert provenance["folding_model"]["configuration"]["salt_molar"] == 0.1


@pytest.mark.parametrize("gene_b", ["SELE", "ENSG00000007908"])
def test_one_gene_can_supply_both_inputs_as_two_windows_of_its_transcript(
    auth_client, csv_upload, media_root, django_capture_on_commit_callbacks, gene_b
):
    run_id = _submit_and_run(
        auth_client,
        csv_upload,
        django_capture_on_commit_callbacks,
        params=_params(
            and_inputs={"gene_a": "SELE", "gene_b": gene_b},
            and_gate={**FAST_AND_GATE, "windows_per_gene": 1},
        ),
    )

    assert auth_client.get(f"/api/runs/{run_id}").json()["status"] == RunStatus.COMPLETED
    listing = auth_client.get(f"/api/runs/{run_id}/candidates").json()
    assert listing["count"] > 0
    detail = auth_client.get(f"/api/candidates/{listing['items'][0]['id']}").json()
    assert {f["gene_symbol"] for f in detail["triggers"]["features"]} == {"SELE"}
    first, second = sorted(detail["design"]["trigger_start_indexes"])
    assert second - first >= 36  # two windows that cannot overlap: they cannot both be bound


def test_yeast_runs_end_to_end(
    auth_client, csv_upload, media_root, django_capture_on_commit_callbacks
):
    """The second advertised host: two real yeast genes (PHM6 and LDM1), not just a capability."""
    table = "gene_id,gene_symbol,log2fc,padj\nYDR281C,PHM6,3.0,0.001\nYER085C,LDM1,2.6,0.001\n"
    run_id = _submit_and_run(
        auth_client,
        csv_upload,
        django_capture_on_commit_callbacks,
        table=table,
        organism="yeast",
        params=_params(and_inputs={"gene_a": "YDR281C", "gene_b": "YER085C"}),
    )

    assert auth_client.get(f"/api/runs/{run_id}").json()["status"] == RunStatus.COMPLETED
    listing = auth_client.get(f"/api/runs/{run_id}/candidates").json()
    assert listing["count"] > 0
    detail = auth_client.get(f"/api/candidates/{listing['items'][0]['id']}").json()
    assert detail["design"]["host"] == "yeast"
    assert set(detail["design"]["and_gate"]["states"]) == {"alone", "+A", "+B", "+A+B"}


# --- Rejected candidates and failed inputs stay visible -----------------------------------------


def test_when_every_candidate_is_rejected_the_run_completes_with_the_reasons(
    auth_client, csv_upload, media_root, django_capture_on_commit_callbacks
):
    """A scoring hard filter nothing can meet: nothing is ranked, nothing is dropped."""
    impossible = {
        "hard_filters": [
            {"metric": "predicted_leakage", "maximum": 0.0, "reason": "No leakage tolerated."}
        ]
    }
    run_id = _submit_and_run(
        auth_client,
        csv_upload,
        django_capture_on_commit_callbacks,
        params=_params(scoring=impossible),
    )

    assert auth_client.get(f"/api/runs/{run_id}").json()["status"] == RunStatus.COMPLETED
    accepted = auth_client.get(f"/api/runs/{run_id}/candidates").json()
    everything = auth_client.get(f"/api/runs/{run_id}/candidates?include_rejected=true").json()
    assert accepted["count"] == 0
    assert everything["count"] > 0
    for candidate in everything["items"]:
        assert candidate["is_rejected"] and candidate["rank"] is None
        assert "No leakage tolerated" in candidate["rejection_reason"]


def test_an_input_gene_that_is_not_in_the_table_fails_the_run_with_the_reason(
    auth_client, csv_upload, media_root, django_capture_on_commit_callbacks
):
    run_id = _submit_and_run(
        auth_client,
        csv_upload,
        django_capture_on_commit_callbacks,
        params=_params(and_inputs={"gene_a": "SELE", "gene_b": "TP53"}),
    )

    status = auth_client.get(f"/api/runs/{run_id}").json()
    assert status["status"] == RunStatus.FAILED
    assert "not in the submitted differential-expression table" in status["error_summary"]
    assert auth_client.get(f"/api/runs/{run_id}/candidates").json()["count"] == 0


def test_a_down_regulated_input_gene_is_refused_not_silently_dropped(
    auth_client, csv_upload, media_root, django_capture_on_commit_callbacks
):
    table = AND_TABLE.replace("ICAM1,2.6", "ICAM1,-2.6")
    run_id = _submit_and_run(
        auth_client, csv_upload, django_capture_on_commit_callbacks, table=table
    )

    status = auth_client.get(f"/api/runs/{run_id}").json()
    assert status["status"] == RunStatus.FAILED
    assert "ENSG00000090339" in status["error_summary"]
    assert "up-regulated" in status["error_summary"]


# --- Unsupported combinations are rejected clearly, before any run is queued --------------------


@pytest.mark.parametrize(
    "overrides, message",
    [
        pytest.param(
            {"input_mode": "direct", "trigger_sequence": "AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGG"},
            "differential-expression table",
            id="a-pasted-sequence-cannot-name-two-inputs",
        ),
        pytest.param(
            {"organism": "ecoli"},
            "not production supported for ecoli",
            id="a-bacterial-host-is-not-offered",
        ),
        pytest.param(
            {"params": _params(constraints={"max_triggers": 1})},
            "exactly 2 inputs",
            id="max_triggers-must-say-two",
        ),
        pytest.param(
            {"params": _params(constraints={"max_triggers": 2, "max_circuit_gates": 2})},
            "max_circuit_gates must be 1",
            id="one-gate-not-a-circuit-of-gates",
        ),
        pytest.param(
            {"params": {k: v for k, v in _params().items() if k != "and_inputs"}},
            "Name the two input genes",
            id="the-input-genes-are-required",
        ),
        pytest.param(
            {"params": _params(and_inputs={"gene_a": "SELE"})},
            "exactly gene_a and gene_b",
            id="both-genes-are-required",
        ),
        pytest.param(
            {"params": _params(and_gate={"n_samples": 5})},
            "and_gate.n_samples",
            id="settings-are-range-checked",
        ),
        pytest.param(
            {"params": _params(and_gate={"colour": "red"})},
            "colour",
            id="unknown-settings-are-rejected-by-name",
        ),
        pytest.param(
            {"gate_families": [AND_FAMILY, "eukaryotic_toehold"]},
            "cannot be combined with single-input",
            id="a-two-input-run-is-not-mixed-with-single-input-families",
        ),
        pytest.param(
            {"gate_families": ["toehold_and"]},
            "not production supported",
            id="the-unbuilt-and-chemistries-stay-refused",
        ),
    ],
)
def test_unsupported_and_submissions_are_rejected_with_a_clear_message(
    auth_client, csv_upload, media_root, overrides, message
):
    payload = {
        "input_mode": "de",
        "dataset_id": _upload(auth_client, csv_upload),
        "organism": "human",
        "gate_families": [AND_FAMILY],
        "params": _params(),
    }
    payload.update(overrides)
    if payload["input_mode"] == "direct":
        payload["dataset_id"] = None

    response = _submit(auth_client, **payload)

    assert response.status_code == 422, response.content
    assert message in json.dumps(response.json())
    assert AnalysisRun.objects.count() == 0


def test_and_blocks_are_rejected_on_a_single_input_gate(auth_client, csv_upload, media_root):
    response = _submit(
        auth_client,
        input_mode="de",
        dataset_id=_upload(auth_client, csv_upload),
        organism="human",
        gate_families=["eukaryotic_toehold"],
        params={"and_inputs": {"gene_a": "SELE", "gene_b": "ICAM1"}},
    )

    assert response.status_code == 422
    assert "applies only to a two-input AND gate" in json.dumps(response.json())


def test_a_misspelled_and_field_is_a_422_naming_the_mistake(auth_client, csv_upload, media_root):
    response = _submit(
        auth_client,
        input_mode="de",
        dataset_id=_upload(auth_client, csv_upload),
        organism="human",
        gate_families=[AND_FAMILY],
        params=_params(and_inputs={"gene_a": "SELE", "gene_c": "ICAM1"}),
    )

    assert response.status_code == 422
    assert "gene_c" in json.dumps(response.json())


# --- Existing single-input runs are unchanged ---------------------------------------------------


def test_a_single_input_run_still_works_and_its_export_has_no_and_columns(
    auth_client, media_root, django_capture_on_commit_callbacks
):
    from apps.analyses.tasks import run_analysis

    with django_capture_on_commit_callbacks():
        run_id = _submit(
            auth_client,
            input_mode="direct",
            trigger_sequence="AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA",
            organism="ecoli",
            params={
                "payload": {"outputs": ["other"], "custom_sequence": "ATGGCTGCTTAA"},
                "budget": {"max_designs": 3},
            },
        ).json()["id"]
    run_analysis(run_id)

    assert auth_client.get(f"/api/runs/{run_id}").json()["status"] == RunStatus.COMPLETED
    header = auth_client.get(f"/api/runs/{run_id}/export.csv").content.decode().splitlines()[0]
    assert "and_on_pct" not in header
    listing = auth_client.get(f"/api/runs/{run_id}/candidates").json()
    detail = auth_client.get(f"/api/candidates/{listing['items'][0]['id']}").json()
    assert "and_gate" not in detail["design"]
    assert len(detail["triggers"]["features"]) == 1
