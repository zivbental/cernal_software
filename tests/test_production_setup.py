"""Production preparation uses isolated directories and never controls real services."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("production", ROOT / "tools/production.py")
production = importlib.util.module_from_spec(spec)
spec.loader.exec_module(production)


@pytest.fixture
def prepared(tmp_path):
    if os.name == "nt":
        pytest.skip("Production templates target Linux; run these regressions in WSL/Linux")
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "manage.py").touch()
    output = tmp_path / "config"
    production.prepare(root, output, "app.example.org", "appuser", "appgroup", 100)
    config = output / "cernal.env"
    config.write_text(config.read_text().replace(production.PLACEHOLDER, "test-only-" + "x" * 64))
    return root, output, config


def test_prepare_preserves_secret_custom_settings_and_data(prepared):
    root, output, config = prepared
    config.write_text(config.read_text() + "CUSTOM_OPERATOR_SETTING=retained\n")
    (root / "var/cernal.db").write_bytes(b"untouched database")
    (root / "var/media/private.txt").write_text("untouched media")
    before = {p: p.read_bytes() for p in output.iterdir()}
    production.prepare(root, output, "app.example.org", "appuser", "appgroup", 100)
    assert before == {p: p.read_bytes() for p in output.iterdir()}
    assert (root / "var/cernal.db").read_bytes() == b"untouched database"
    assert (root / "var/media/private.txt").read_text() == "untouched media"
    for name in (
        "logs",
        "media/datasets",
        "media/artifacts",
        "result-staging",
        "worker-status",
        "staticfiles",
    ):
        assert (root / "var" / name).is_dir()


def test_conflicting_domain_preserves_all_files(prepared):
    root, output, _ = prepared
    before = {p: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(ValueError, match="conflict"):
        production.prepare(root, output, "different.example.org", "appuser", "appgroup", 100)
    assert before == {p: p.read_bytes() for p in output.iterdir()}


@pytest.mark.parametrize(
    "domain",
    ["https://host.example", "host.example:443", "*.example.org", "x\nuser", "a/b", "-bad.example"],
)
def test_domain_injection_rejected(domain):
    with pytest.raises(ValueError, match="hostname"):
        production.domain_name(domain)


@pytest.mark.parametrize(
    "path", ["relative", "/opt/with space", "/opt/$HOME", "/opt/a/../b", "/opt/a\nExecStart=x"]
)
def test_ambiguous_paths_rejected(path):
    with pytest.raises(ValueError, match="paths"):
        production.deployment_path(path)


def test_templates_use_same_paths_and_upload_budget(prepared):
    root, output, config = prepared
    env = production.environment(config)
    assert env["DATABASE_URL"] == f"sqlite:///{root}/var/cernal.db"
    for unit in output.glob("*.service"):
        text = unit.read_text()
        assert "@@" not in text and "/opt/cernal" not in text
        assert f"WorkingDirectory={root}" in text
        assert f"EnvironmentFile={config}" in text
        assert f"ReadWritePaths={root}/var" in text
        assert "User=appuser" in text and "Group=appgroup" in text
    app, proxy = production.upload_limits(100)
    assert app == 104857600 and proxy == 106954752
    assert f"max_size {proxy}" in (output / "Caddyfile").read_text()
    assert production.upload_limits(1)[1] > production.upload_limits(1)[0]
    assert production.upload_limits(1024)[0] == 1024**3
    for value in (0, -1, 1025):
        with pytest.raises(ValueError, match="MAX_DATASET_MB"):
            production.upload_limits(value)


def test_runtime_file_conflict_is_actionable(tmp_path):
    from config.runtime import ensure_runtime_directories

    (tmp_path / "logs").touch()
    with pytest.raises(RuntimeError, match=r"Cannot prepare runtime directory.*logs"):
        ensure_runtime_directories(tmp_path, tmp_path / "media", tmp_path / "staticfiles")


def test_fresh_production_initialization_before_file_logging(tmp_path):
    env = dict(
        os.environ,
        DJANGO_SETTINGS_MODULE="config.settings.prod",
        SECRET_KEY="test-only-" + "x" * 64,
        ALLOWED_HOSTS="app.example.org",
        CERNAL_VAR_DIR=str(tmp_path / "new-var"),
        MEDIA_ROOT=str(tmp_path / "new-var/media"),
        DATABASE_URL=f"sqlite:///{tmp_path}/new-var/cernal.db",
        PYTHONPATH=str(ROOT / "src"),
    )
    code = 'import django; django.setup(); import logging; logging.warning("fresh startup test")'
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "fresh startup test" in (tmp_path / "new-var/logs/cernal.log").read_text()
    assert not (tmp_path / "new-var/cernal.db").exists()


def test_install_requires_explicit_fresh_database_and_preserves_existing(prepared, monkeypatch):
    root, _, config = prepared
    monkeypatch.setattr(production, "ROOT", root)
    commands = []

    def fake_run(command, *_):
        commands.append(command)
        (root / ".venv").mkdir(exist_ok=True)

    monkeypatch.setattr(production, "run", fake_run)
    with pytest.raises(ValueError, match="--initialize-database"):
        production.install(root, config)
    production.install(root, config, initialize=True)
    assert any(c[1:] == ["tools/install_data.py"] for c in commands)
    assert not any("createsuperuser" in c for c in commands)
    (root / "var/cernal.db").write_text("existing")
    production.install(root, config)
    assert (root / "var/cernal.db").read_text() == "existing"
    with pytest.raises(ValueError, match="already exists"):
        production.install(root, config, initialize=True)
    with pytest.raises(ValueError, match="interactive"):
        production.install(root, config, admin=True)


def test_relocated_venv_is_not_rewritten(prepared, monkeypatch):
    root, _, config = prepared
    monkeypatch.setattr(production, "ROOT", root)
    (root / ".venv").mkdir()
    (root / ".venv/cernal-install-root").write_text("/old/location")
    with pytest.raises(ValueError, match="never patch shebangs"):
        production.install(root, config, initialize=True)
    assert (root / ".venv/cernal-install-root").read_text() == "/old/location"


def test_admin_creation_requires_explicit_interactive_opt_in(prepared, monkeypatch):
    root, _, config = prepared
    monkeypatch.setattr(production, "ROOT", root)
    monkeypatch.setattr(production.sys.stdin, "isatty", lambda: True)
    commands = []

    def fake_run(command, *_):
        commands.append(command)
        (root / ".venv").mkdir(exist_ok=True)

    monkeypatch.setattr(production, "run", fake_run)
    production.install(root, config, initialize=True, admin=True)
    assert commands[-1][1:] == ["manage.py", "createsuperuser"]


def test_failed_dependency_install_stops_before_database_changes(prepared, monkeypatch):
    root, _, config = prepared
    monkeypatch.setattr(production, "ROOT", root)
    commands = []

    def fail(command, *_):
        commands.append(command)
        raise ValueError("dependency unavailable")

    monkeypatch.setattr(production, "run", fail)
    with pytest.raises(ValueError, match="dependency unavailable"):
        production.install(root, config, initialize=True)
    assert len(commands) == 1
    assert not (root / "var/cernal.db").exists()


def test_step_failure_message_does_not_expose_environment():
    with patch.object(production.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
        with pytest.raises(ValueError, match=r"step failed.*existing data/config preserved"):
            production.run(["uv", "sync"], ROOT, {"SECRET_KEY": "not-for-output"})


def test_status_never_calls_missing_database_ready(prepared, monkeypatch, capsys):
    root, _, config = prepared
    monkeypatch.setattr(production.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    monkeypatch.setattr(production, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert production.status(root, config) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["database"] == "missing"
    for name in ("data", "web", "worker", "reconciler_service", "screening_inventory"):
        assert report[name] == "unavailable"


@pytest.mark.django_db
def test_dataset_file_boundary_remains_application_enforced(user, settings, tmp_path):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.datasets.services import DatasetValidationError, create_dataset

    settings.MAX_DATASET_MB = 1
    settings.MEDIA_ROOT = tmp_path
    with patch("apps.datasets.services.validate_expression_file", return_value={"errors": []}):
        at_limit = SimpleUploadedFile("boundary.csv", b"x" * (1024 * 1024))
        assert create_dataset(uploaded_file=at_limit, user=user).size_bytes == 1024 * 1024
        over_limit = SimpleUploadedFile("over.csv", b"x" * (1024 * 1024 + 1))
        with pytest.raises(DatasetValidationError, match="larger"):
            create_dataset(uploaded_file=over_limit, user=user)
