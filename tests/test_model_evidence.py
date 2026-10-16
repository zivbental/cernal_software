"""Missing scientific inputs cannot produce an accepted quantitative snapshot."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_barrier_rows_fail_with_actual_requested_path(tmp_path, capsys):
    assert tool("barrier_report").main(["--barriers", str(tmp_path)]) == 2
    assert str(tmp_path) in capsys.readouterr().out


def test_snapshot_audit_is_portable_and_rejects_added_claims(tmp_path, monkeypatch):
    audit = tool("wiki_audit_numbers")
    monkeypatch.chdir(tmp_path)
    assert audit.main([]) == 0
    changed = tmp_path / "changed.html"
    original = audit.PAGE.read_text(encoding="utf-8")
    for addition in ("<p>Correlation is 0.528.</p>", '<img src="unsupported.svg">'):
        changed.write_text(original + addition, encoding="utf-8")
        assert audit.main(["--page", str(changed)]) == 1
    assert audit.main(["--page", str(tmp_path / "missing.html")]) == 1
