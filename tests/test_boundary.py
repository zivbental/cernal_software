"""Enforces the Platform ⇄ Engine boundary.

**This is the most important test in the repository.** It is what turns
docs/architecture.md §3 from a convention into a fact, and it is what makes the
engine extractable into its own service later without a rewrite.

If it fails, do not add an exception. The failure means the two halves of the system
have started to fuse, which is the one outcome this architecture exists to prevent.

An AST scan rather than an import hook: it is fast, has no side effects, and catches
imports that a runtime check would miss — inside functions, inside ``if TYPE_CHECKING``,
and inside branches that never execute.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
ENGINE = SRC / "engine"
PLATFORM_DIRS = [SRC / "apps", SRC / "api", SRC / "config"]

#: The engine may not import these.
FORBIDDEN_IN_ENGINE = ("django", "apps", "api", "config")

#: Platform code may import only these two engine modules.
ALLOWED_ENGINE_MODULES = ("engine.contract", "engine.client")


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "migrations" not in p.parts)


def _imported_modules(path: Path) -> list[tuple[str, int]]:
    """Every absolute module name imported by a file, with its line number.

    Relative imports (``from . import x``) are package-internal and are skipped.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.append((node.module, node.lineno))

    return found


def _root_of(module: str) -> str:
    return module.split(".")[0]


def test_engine_directory_exists():
    assert ENGINE.is_dir(), "src/engine/ is missing — the boundary has no subject"
    assert _python_files(ENGINE), "src/engine/ contains no Python files"


@pytest.mark.parametrize("path", _python_files(ENGINE), ids=lambda p: str(p.relative_to(SRC)))
def test_engine_imports_no_platform_code(path: Path):
    """src/engine/ must never import Django or Platform code (§3)."""
    violations = [
        f"{path.relative_to(SRC)}:{lineno} imports '{module}'"
        for module, lineno in _imported_modules(path)
        if _root_of(module) in FORBIDDEN_IN_ENGINE
    ]
    assert not violations, (
        "The engine imported Platform code:\n  "
        + "\n  ".join(violations)
        + "\n\nThe engine must receive plain paths and dataclasses, never models, "
        "settings or requests. See docs/architecture.md §3."
    )


@pytest.mark.parametrize(
    "path",
    [p for d in PLATFORM_DIRS if d.is_dir() for p in _python_files(d)],
    ids=lambda p: str(p.relative_to(SRC)),
)
def test_platform_imports_only_the_engine_contract(path: Path):
    """Platform code may import only engine.contract and engine.client (§3).

    Reaching into engine.pipeline, engine.gates or engine.scoring would couple the
    product to the engine's internals, which is what makes the engine unextractable.
    """
    violations = [
        f"{path.relative_to(SRC)}:{lineno} imports '{module}'"
        for module, lineno in _imported_modules(path)
        if _root_of(module) == "engine" and module not in ALLOWED_ENGINE_MODULES
    ]
    assert not violations, (
        "Platform code reached into the engine's internals:\n  "
        + "\n  ".join(violations)
        + f"\n\nAllowed engine imports: {', '.join(ALLOWED_ENGINE_MODULES)}. "
        "See docs/architecture.md §3."
    )


def test_engine_is_importable_without_django():
    """The engine must import in a process where Django was never configured.

    Catches a module-level ``django.setup()`` or settings access that the AST scan
    would see as a non-forbidden name.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {str(SRC)!r}); "
            "import engine.contract, engine.client, engine.artifacts, engine.errors; "
            "import engine.gates.registry, engine.scoring.profiles, engine.scoring.normalize; "
            "assert 'django' not in sys.modules, "
            "sorted(m for m in sys.modules if 'django' in m)",
        ],
        capture_output=True,
        text=True,
        env={"PATH": ""},
    )
    assert result.returncode == 0, (
        "Importing the engine pulled in Django or failed outright:\n" + result.stderr
    )
