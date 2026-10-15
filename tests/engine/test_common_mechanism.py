"""Synthetic contract/process fixtures only: these are not biological validation."""

import copy
import hashlib
import json
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from engine.common_mechanism import (
    POLICY_VERSION,
    CommonMechanismAdapter,
    configured_final_screens,
    inventory_digest,
    read_json,
    screen_final_batch,
)
from engine.safety import AdapterStatus, Decision, LocalScreeningManifest, SequenceSubmission


@pytest.fixture
def submission():
    return SequenceSubmission("synthetic", "ACGU" * 25, "plasmid", "test-only")


def native_result(submissions, status="Pass"):
    """Minimal native v2.1.0/JSON0.6 fields, NOT an actual commec report."""
    return {
        "commec_info": {"commec_version": "2.1.0", "json_output_version": "0.6"},
        "query_info": {
            "number_of_queries": len(submissions),
            "total_query_length": sum(len(s.sequence) for s in submissions),
        },
        "database_info": {
            "revisions": dict.fromkeys(
                ("biorisk", "best_match", "low_concern", "control_lists"), "1.0"
            )
        },
        "queries": {
            f"q{i:06d}": {
                "query": f"q{i:06d}",
                "length": len(s.sequence),
                "hits": [],
                "status": {
                    "screen_status": status,
                    "biorisk": "Pass",
                    "protein_taxonomy": "Pass",
                    "nucleotide_taxonomy": "Pass",
                    "low_concern": "Skip",
                },
            }
            for i, s in enumerate(submissions)
        },
    }


@pytest.fixture
def adapter(tmp_path, submission):
    database = tmp_path / "db"
    database.mkdir()
    (database / "synthetic.txt").write_text("mock database, no biological references")
    files = {"synthetic.txt": hashlib.sha256((database / "synthetic.txt").read_bytes()).hexdigest()}
    program = tmp_path / "mock-commec"
    # Exercises real bounded subprocess and temporary-file orchestration, not real screening.
    report = native_result((submission,))
    program.write_text(f"""#!{sys.executable}
import json, pathlib, sys
assert "--skip-tx" not in sys.argv and "-y" not in sys.argv
assert sys.argv[sys.argv.index("--regions") + 1] == "all"
prefix = pathlib.Path(sys.argv[sys.argv.index("-o") + 1])
assert pathlib.Path(sys.argv[-1]).read_text() == ">q000000\\n{"ACGT" * 25}\\n"
(prefix.parent / "input_result").mkdir()
(prefix.parent / "input_result" / "result_config.yaml").write_text(
    "skip_taxonomy_search: false\\nskip_nt_search: false\\n"
    "auto_update_databases: false\\nresume: false\\n")
data = {report!r}
data["query_info"]["file"] = sys.argv[-1]
prefix.with_suffix(".output.json").write_text(json.dumps(data))
""")
    program.chmod(0o700)
    software = {str(program): hashlib.sha256(program.read_bytes()).hexdigest()}
    now = datetime.now(UTC)
    manifest = LocalScreeningManifest(
        "ibbis-common-mechanism",
        "2.1.0",
        "synthetic-test-only",
        inventory_digest(files),
        now - timedelta(seconds=1),
        now + timedelta(hours=1),
        policy_version=POLICY_VERSION,
        software_sha256=inventory_digest(software),
    )
    return CommonMechanismAdapter(
        manifest, program, database, files, report["database_info"]["revisions"], software
    )


def test_actual_process_mock_and_original_rna_identity(adapter, submission):
    result = screen_final_batch((submission,), adapter)[0]
    assert result.decision == Decision.PASS
    assert result.screening_status == "screened"
    assert result.sequence_sha256 == hashlib.sha256(submission.sequence.encode()).hexdigest()
    assert "safe" not in " ".join(result.reasons).lower()


@pytest.mark.parametrize(
    "status,expected",
    [
        ("Pass", AdapterStatus.COMPLETE),
        ("Flag", AdapterStatus.COMPLETE),
        ("Warning", AdapterStatus.COMPLETE),
        ("Flag (Cleared)", AdapterStatus.COMPLETE),
        ("Warning (Cleared)", AdapterStatus.COMPLETE),
        ("Error", AdapterStatus.FAILED),
        ("Incomplete", AdapterStatus.INCONCLUSIVE),
        ("Skip", AdapterStatus.INCONCLUSIVE),
        ("Skip (too short)", AdapterStatus.INCONCLUSIVE),
        ("Skip (too long)", AdapterStatus.INCONCLUSIVE),
        ("Pass (Skipped Taxonomy)", AdapterStatus.INCONCLUSIVE),
        ("-", AdapterStatus.INCONCLUSIVE),
        ("new-unknown-status", AdapterStatus.INCONCLUSIVE),
    ],
)
def test_every_native_status_is_explicit(adapter, submission, status, expected):
    evidence = adapter.parse_result(native_result((submission,), status), (submission,))[0]
    assert evidence.adapter_status == expected
    if status in {"Flag", "Warning", "Flag (Cleared)", "Warning (Cleared)"}:
        from engine.safety import SafetyGate

        result = SafetyGate().evaluate(submission, evidence, now=datetime.now(UTC))
        assert result.decision == Decision.BLOCK
        assert not result.release_allowed
        assert result.screening_status == "flagged"
        assert result.reasons == ("screening flag requires review",)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["commec_info"].update(commec_version="2.2.0"),
        lambda d: d["commec_info"].update(json_output_version="0.7"),
        lambda d: d["database_info"]["revisions"].update(biorisk="1.1"),
        lambda d: d["query_info"].update(number_of_queries=0),
        lambda d: d["query_info"].update(total_query_length=101),
        lambda d: d["queries"].update(extra=d["queries"]["q000000"]),
        lambda d: d["queries"]["q000000"].update(query="wrong"),
        lambda d: d["queries"]["q000000"].update(length=True),
        lambda d: d["queries"]["q000000"].update(hits={}),
        lambda d: d["queries"]["q000000"]["status"].update(biorisk="Skip"),
        lambda d: d["queries"]["q000000"]["status"].update(protein_taxonomy="Error"),
        lambda d: d["queries"]["q000000"]["status"].update(nucleotide_taxonomy="Incomplete"),
        lambda d: d["queries"]["q000000"].update(hits=[{"recommendation": {"status": "Flag"}}]),
        lambda d: d["queries"].clear(),
    ],
)
def test_incomplete_contradictory_or_mismatched_outputs_hold(adapter, submission, mutation):
    data = native_result((submission,))
    mutation(data)
    assert adapter.parse_result(data, (submission,))[0].adapter_status == AdapterStatus.INCONCLUSIVE


@pytest.mark.parametrize("value", [None, [], "", 7, {"queries": []}])
def test_malformed_native_report_holds(adapter, submission, value):
    assert (
        adapter.parse_result(value, (submission,))[0].adapter_status == AdapterStatus.INCONCLUSIVE
    )


@pytest.mark.parametrize("length", [0, 40, 100001])
def test_unsupported_lengths_are_never_truncated(adapter, submission, length):
    item = replace(submission, sequence="A" * length)
    assert adapter.screen(item).adapter_status == AdapterStatus.INCONCLUSIVE


def test_modified_database_and_software_hold(adapter, submission):
    (adapter.database / "synthetic.txt").write_text("changed")
    assert adapter.screen(submission).adapter_status == AdapterStatus.UNAVAILABLE
    adapter.executable.write_text("changed")
    assert adapter.screen(submission).adapter_status == AdapterStatus.UNAVAILABLE


def test_unlisted_database_file_holds(adapter, submission):
    (adapter.database / "new.txt").write_text("new")
    assert adapter.screen(submission).adapter_status == AdapterStatus.UNAVAILABLE


def test_missing_installation_and_invalid_configuration_hold(adapter, submission, tmp_path):
    assert (
        replace(adapter, executable=Path("/not-installed")).screen(submission).adapter_status
        == AdapterStatus.UNAVAILABLE
    )
    assert not configured_final_screens((submission,), str(tmp_path / "missing.json"))[
        0
    ].release_allowed


def test_duplicate_json_keys_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"queries": {}, "queries": {}}')
    with pytest.raises(ValueError, match="duplicate"):
        read_json(path)


def test_batch_identity_mismatch_holds_whole_batch(adapter, submission):
    batch = (submission, replace(submission, sequence="ACGU" * 30))
    data = native_result(batch)
    data["queries"]["q000001"]["length"] = 100
    assert all(
        e.adapter_status == AdapterStatus.INCONCLUSIVE for e in adapter.parse_result(data, batch)
    )


def test_malformed_report_does_not_mutate_input(adapter, submission):
    data = native_result((submission,))
    original = copy.deepcopy(data)
    adapter.parse_result(data, (submission,))
    assert data == original


def test_pipeline_screens_final_switch_and_complete_construct(
    monkeypatch, make_request, progress, adapter
):
    from engine import pipeline
    from engine.client import LocalEngine
    from engine.safety import SafetyGate

    seen = []

    def mock_screen(submissions, path, **kwargs):
        assert path.endswith("test-only-manifest.json")
        seen.extend(submissions)
        data = native_result(submissions)
        return tuple(
            SafetyGate().evaluate(s, e, now=datetime.now(UTC))
            for s, e in zip(submissions, adapter.parse_result(data, submissions), strict=True)
        )

    config = adapter.database.parent / "test-only-manifest.json"
    config.write_text(
        json.dumps({"manifest": asdict(adapter.manifest)}, default=lambda d: d.isoformat())
    )
    monkeypatch.setenv("CERNAL_COMMEC_MANIFEST", str(config))
    monkeypatch.setattr(pipeline, "configured_final_screens", mock_screen)
    result = LocalEngine().run(
        make_request(
            input_mode="direct",
            trigger_sequence="AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA",
            organism="ecoli",
        ),
        progress,
    )
    accepted = [c for c in result.candidates if not c.is_rejected]
    assert accepted and len(seen) == 2 * len(accepted)
    by_id = {s.sequence_id: s for s in seen}
    for candidate in accepted:
        switch = by_id[f"{candidate.ref}:switch"]
        construct = by_id[f"{candidate.ref}:plasmid"]
        assert switch.sequence == candidate.design["switch_sequence"]
        assert construct.sequence_sha256 == candidate.design["construct_sha256"]
        assert len(construct.sequence) > len(switch.sequence)
        for kind in ("sequence_fasta", "genbank", "sbol"):
            assert any(
                a.kind == kind and a.candidate_ref == candidate.ref for a in result.artifacts
            )


def test_final_construct_flag_withholds_all_sequence_exports(
    monkeypatch, make_request, progress, adapter
):
    from engine import pipeline
    from engine.client import LocalEngine
    from engine.safety import SafetyGate

    def mock_screen(submissions, path, **kwargs):
        data = native_result(submissions)
        for i, s in enumerate(submissions):
            if s.sequence_id.endswith(":plasmid"):
                data["queries"][f"q{i:06d}"]["status"]["screen_status"] = "Flag"
        return tuple(
            SafetyGate().evaluate(s, e, now=datetime.now(UTC))
            for s, e in zip(submissions, adapter.parse_result(data, submissions), strict=True)
        )

    config = adapter.database.parent / "test-only-manifest.json"
    config.write_text(
        json.dumps({"manifest": asdict(adapter.manifest)}, default=lambda d: d.isoformat())
    )
    monkeypatch.setenv("CERNAL_COMMEC_MANIFEST", str(config))
    monkeypatch.setattr(pipeline, "configured_final_screens", mock_screen)
    result = LocalEngine().run(
        make_request(
            input_mode="direct",
            trigger_sequence="AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA",
            organism="ecoli",
        ),
        progress,
    )
    assert result.candidates
    assert not any(a.kind in {"sequence_fasta", "genbank", "sbol"} for a in result.artifacts)
    for c in result.candidates:
        if not c.is_rejected:
            assert c.design["sequence_release"]["switch"]["screening_status"] == "screened"
            assert c.design["sequence_release"]["plasmid"]["screening_status"] == "flagged"


def repin_mock_program(adapter, text):
    adapter.executable.write_text(text)
    software = {
        str(adapter.executable): hashlib.sha256(adapter.executable.read_bytes()).hexdigest()
    }
    return replace(
        adapter,
        software_files=software,
        manifest=replace(adapter.manifest, software_sha256=inventory_digest(software)),
    )


@pytest.mark.parametrize(
    "change,expected",
    [
        (
            lambda s: s.replace("skip_nt_search: false", "skip_nt_search: true"),
            AdapterStatus.INCONCLUSIVE,
        ),
        (
            lambda s: s.replace(
                'data["query_info"]["file"] = sys.argv[-1]',
                'data["query_info"]["file"] = "other-job"',
            ),
            AdapterStatus.INCONCLUSIVE,
        ),
        (lambda s: f"#!{sys.executable}\nraise SystemExit(3)\n", AdapterStatus.FAILED),
        (lambda s: f"#!{sys.executable}\n", AdapterStatus.FAILED),
    ],
)
def test_process_error_config_skip_or_wrong_input_holds(adapter, submission, change, expected):
    adapter = repin_mock_program(adapter, change(adapter.executable.read_text()))
    assert adapter.screen(submission).adapter_status == expected


def test_real_timeout_of_mock_process_holds(adapter, submission):
    adapter = repin_mock_program(adapter, f"#!{sys.executable}\nimport time\ntime.sleep(20)\n")
    adapter = replace(adapter, timeout_seconds=1)
    assert adapter.screen(submission).adapter_status == AdapterStatus.TIMEOUT


def test_inventory_checked_twice_per_whole_run_and_bounded_batches(
    adapter, submission, monkeypatch
):
    from engine.safety import ScreeningEvidence

    checks, sizes = [], []
    real_verify = CommonMechanismAdapter._verify_installation

    def verify(self):
        checks.append(1)
        real_verify(self)

    def batch(self, items):
        sizes.append(len(items))
        return tuple(ScreeningEvidence(self.manifest, AdapterStatus.COMPLETE) for _ in items)

    monkeypatch.setattr(CommonMechanismAdapter, "_verify_installation", verify)
    monkeypatch.setattr(CommonMechanismAdapter, "_screen_one_batch", batch)
    results = adapter.screen_many((submission,) * 65)
    assert len(results) == 65 and sizes == [64, 1] and len(checks) == 2


def test_database_changed_during_last_batch_invalidates_every_result(
    adapter, submission, monkeypatch
):
    from engine.safety import ScreeningEvidence

    def batch(self, items):
        (self.database / "synthetic.txt").write_text("changed during screening")
        return tuple(ScreeningEvidence(self.manifest, AdapterStatus.COMPLETE) for _ in items)

    monkeypatch.setattr(CommonMechanismAdapter, "_screen_one_batch", batch)
    assert all(
        e.adapter_status == AdapterStatus.UNAVAILABLE
        for e in adapter.screen_many((submission,) * 65)
    )


def test_cancellation_between_batches_produces_no_release(adapter, submission):
    from engine.errors import JobCancelled

    with pytest.raises(JobCancelled):
        adapter.screen_many((submission,), on_batch=lambda: False)


def test_active_deployment_rotation_and_revocation_hold(adapter, submission, monkeypatch, tmp_path):
    from engine.safety import SafetyGate, stored_release_allowed

    evidence = adapter.parse_result(native_result((submission,)), (submission,))[0]
    result = SafetyGate().evaluate(submission, evidence, now=datetime.now(UTC))
    design = {
        "switch_sequence": submission.sequence,
        "construct_sha256": submission.sequence_sha256,
        "sequence_release": {"switch": result.release_record(), "plasmid": result.release_record()},
    }
    config = tmp_path / "active.json"
    active = {"manifest": asdict(adapter.manifest)}
    config.write_text(json.dumps(active, default=lambda d: d.isoformat()))
    monkeypatch.setenv("CERNAL_COMMEC_MANIFEST", str(config))
    assert stored_release_allowed(design)
    active["manifest"]["database_sha256"] = "f" * 64
    config.write_text(json.dumps(active, default=lambda d: d.isoformat()))
    assert not stored_release_allowed(design)
    monkeypatch.delenv("CERNAL_COMMEC_MANIFEST")
    assert not stored_release_allowed(design)


def test_operator_config_loads_and_invokes_complete_mock_pipeline(adapter, submission, tmp_path):
    config = {
        "manifest": asdict(adapter.manifest),
        "executable": str(adapter.executable),
        "database": str(adapter.database),
        "files": adapter.files,
        "software_files": adapter.software_files,
        "revisions": adapter.revisions,
        "timeout_seconds": 10,
        "threads": 1,
    }
    path = tmp_path / "deployment.json"
    path.write_text(json.dumps(config, default=lambda d: d.isoformat()))
    result = configured_final_screens((submission,), str(path))[0]
    assert result.decision == Decision.PASS
    assert result.screening_status == "screened"
    assert result.sequence_sha256 == submission.sequence_sha256
