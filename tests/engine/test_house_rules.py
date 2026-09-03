"""Enforces the engine's house rules — the ones CLAUDE.md states in prose.

``tests/test_boundary.py`` guards the Platform ⇄ Engine seam. This file guards everything
*inside* the engine: which module may fold RNA, who may build a tool, which direction an
import may point, and — the one that matters most — which metric names a gate family is
allowed to emit.

**Why these are tests and not a code-review checklist.** Every rule below prevents a
failure that produces a *plausible number*, not a crash. A second ``FoldEngine`` at a
different temperature, a metric name with a typo in it, a ``0.0`` returned where a
measurement failed — none of these raise. They quietly change which design the team
orders from the synthesis company. A reviewer cannot see them; a test can.

**Why AST and not grep.** Almost every rule here is written *about* in a docstring
somewhere in ``src/engine/`` — ``gates/tools/folding.py`` warns you not to touch
``RNA.cvar.temperature``, ``pipeline.py`` sketches ``FoldEngine()`` in a code block,
``gates/crispr.py`` discusses ``OffTargetScanner``. A text search flags all of those and
teaches the team to ignore this file. An AST scan sees only real code, so a failure here
is always a real failure. It also catches what a runtime check would miss: imports inside
functions, inside ``if TYPE_CHECKING``, and inside branches that never execute.

**If a check fails, do not delete it and do not add an exception.** Fix the code, or —
if the rule genuinely no longer holds — change the rule in CLAUDE.md and here in the same
commit, with the reason written down.

No Django, no ViennaRNA, no engine import: these tests read source text and parse it. They
run in milliseconds on a laptop with nothing installed but pytest.
"""

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
ENGINE = SRC / "engine"

# ---------------------------------------------------------------------------
# Rule constants. Each one is the machine-readable half of a sentence in CLAUDE.md.
# ---------------------------------------------------------------------------

#: Import roots that mean "this module folds RNA itself".
#: ``RNA`` is what the ``viennarna`` distribution installs; the others are the libraries
#: someone reaches for when ViennaRNA is inconvenient.
FOLDING_LIBRARIES = ("RNA", "ViennaRNA", "nupack", "seqfold")

#: The only two modules allowed to import a folding library, per docs/ROADMAP.md E1.
#: One does design-side MFE folding with a cache; the other wraps windowed ``RNAplfold``.
#: They share neither cache nor temperature model, which is exactly why there are two and
#: not one — and why there must never be a third.
FOLDING_ADAPTERS = (
    "engine/gates/tools/folding.py",
    "engine/stages/folding.py",
)

#: Tools whose configuration decides what a number *means*. Constructing a second one
#: anywhere is how two incomparable measurements end up on one ranking axis.
SHARED_TOOLS = (
    "FoldEngine",
    "FoldProfiler",
    "OffTargetScanner",
    "MotifScreener",
    "CodonOptimizer",
    "TranslationScorer",
)

#: The one module allowed to call those constructors (``build_tools``).
TOOL_FACTORY = "engine/pipeline.py"

#: Stage-2 tools. A gate family that touches one of these is re-measuring something the
#: pipeline already measured and stored on the record it was handed.
STAGE_ONLY_TOOLS = ("FoldProfiler", "OffTargetScanner")

#: Layer ranks. Longest prefix first — ``gates/tools/`` must match before ``gates/``.
#: An import may point at its own rank or below it, never above.
LAYER_RANKS: tuple[tuple[str, int], ...] = (
    ("engine/domain.py", 0),
    ("engine/sequences.py", 1),
    ("engine/gates/tools/", 2),
    ("engine/gates/", 3),
    ("engine/stages/", 4),
    ("engine/pipeline.py", 5),
)

#: The documented sideways exception. These three are *tools that happen to live beside
#: the stages* because no gate family uses them (see engine/gates/tools/__init__.py).
#: Every other stage-imports-a-stage is a stage doing another stage's job.
STAGE_TOOL_MODULES = frozenset(
    {
        "engine.stages.folding",  # S1 · FoldProfiler
        "engine.stages.off_target",  # S5 · OffTargetScanner
        "engine.stages.motifs",  # S7 · MotifScreener
    }
)

#: Functions whose return value is fed straight into ``engine.scoring``.
MEASURING_FUNCTIONS = ("evaluate_design", "score")

#: Numbers that get used to mean "I could not measure this". Every one of them is a
#: real number to ``normalize_value``. The contract says ``None``.
SENTINEL_NUMBERS = (0, 0.0, -1, -1.0, 999, 999.0, -999, -999.0)

#: Records that must stay immutable, per docs/engine.md §2.2-2.3.
FROZEN_RECORD_MODULES = ("engine/domain.py", "engine/contract.py")


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _python_files(root: Path) -> list[Path]:
    """Every Python source file under ``root``, ignoring generated trees."""
    return sorted(
        p
        for p in root.rglob("*.py")
        if "migrations" not in p.parts and "__pycache__" not in p.parts
    )


def _rel(path: Path) -> str:
    """``src``-relative POSIX path — the form used in every message below."""
    return path.relative_to(SRC).as_posix()


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_modules(path: Path) -> list[tuple[str, int]]:
    """Absolute module names imported by a file, with line numbers.

    Relative imports are package-internal and are skipped, exactly as in
    ``tests/test_boundary.py``.
    """
    found: list[tuple[str, int]] = []
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module, node.lineno))
    return found


def _root_of(module: str) -> str:
    return module.split(".")[0]


def _module_to_relpath(module: str) -> str:
    """``engine.gates.toehold`` → ``engine/gates/toehold.py``.

    Package imports (``engine.stages``) become ``engine/stages/__init__.py`` so they rank
    with the package they name.
    """
    candidate = module.replace(".", "/")
    if (SRC / f"{candidate}.py").is_file():
        return f"{candidate}.py"
    return f"{candidate}/__init__.py"


def _layer_rank(relpath: str) -> int | None:
    """The layer a ``src``-relative path sits in, or ``None`` if it is unranked.

    Unranked on purpose: ``contract``, ``errors``, ``artifacts``, ``store``, ``client``
    and ``scoring/``. The first four are leaves everything may use; ``client`` sits above
    ``pipeline`` and is covered by ``tests/test_boundary.py``; ``scoring`` has its own
    rule below (rule 4), which is stricter than a rank would be.
    """
    for prefix, rank in LAYER_RANKS:
        if relpath == prefix or relpath.startswith(prefix):
            return rank
    return None


def _functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]


def _referenced_names(tree: ast.AST) -> list[tuple[str, int]]:
    """Every identifier the *code* mentions, with its line. Docstrings are not code.

    Covers bare names (``FoldEngine``), attribute access (``folding.FoldEngine``) and
    import aliases (``from x import FoldEngine as F``), which is every way a class can be
    named without writing it as a string.
    """
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.append((node.id, node.lineno))
        elif isinstance(node, ast.Attribute):
            found.append((node.attr, node.lineno))
        elif isinstance(node, ast.ImportFrom | ast.Import):
            for alias in node.names:
                found.append((alias.name.split(".")[-1], node.lineno))
    return found


def _called_names(tree: ast.AST) -> list[tuple[str, int]]:
    """The callee of every call expression, by its final identifier."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            found.append((node.func.id, node.lineno))
        elif isinstance(node.func, ast.Attribute):
            found.append((node.func.attr, node.lineno))
    return found


def _is_sentinel_number(node: ast.AST) -> bool:
    """Is this expression a "measurement failed" magic number?

    ``True``/``False`` are excluded: in Python they are ints, but nobody means ``0.0``
    when they write ``return False``.
    """
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return False
        if isinstance(node.value, int | float) and node.value in SENTINEL_NUMBERS:
            return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "float"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and node.args[0].value.strip().lower() == "nan"
    ):
        return True
    # math.nan / np.nan / numpy.nan
    return isinstance(node, ast.Attribute) and node.attr == "nan"


def _declared_metric_names() -> set[str]:
    """The metric vocabulary, read out of ``scoring/profiles.py`` by AST.

    Parsed rather than imported so this test cannot drift from the profile and needs no
    ``sys.path``: every ``MetricSpec(name="…")`` in that module is a legal metric name.
    """
    tree = _parse(SRC / "engine" / "scoring" / "profiles.py")
    names: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "MetricSpec":
            continue
        for keyword in node.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                if isinstance(keyword.value.value, str):
                    names.add(keyword.value.value)
    return names


def _emitted_metric_names(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[str, int]]:
    """Metric names a measuring function puts into the dict it returns.

    Two idioms are recognised, because those are the two anyone writes:

    1. ``return {"predicted_leakage": ..., ...}`` — string keys of a returned dict.
    2. ``metrics = {}`` / ``metrics["predicted_leakage"] = ...`` / ``return metrics`` —
       string subscript assignments onto a name that is later returned.

    Deliberately narrow. A dict literal used for something else inside the function (a
    codon table, a lookup) is not treated as metric output, so this check has no false
    positives to train the team to ignore.
    """
    returned_names: set[str] = set()
    literal_keys: list[tuple[str, int]] = []

    for node in ast.walk(func):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        if isinstance(node.value, ast.Name):
            returned_names.add(node.value.id)
        elif isinstance(node.value, ast.Dict):
            literal_keys.extend(_string_keys(node.value))

    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            # metrics["name"] = value
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id in returned_names
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            ):
                literal_keys.append((target.slice.value, node.lineno))
            # metrics = {"name": value, ...}
            elif (
                isinstance(target, ast.Name)
                and target.id in returned_names
                and isinstance(node.value, ast.Dict)
            ):
                literal_keys.extend(_string_keys(node.value))

    return literal_keys


def _string_keys(node: ast.Dict) -> list[tuple[str, int]]:
    return [
        (key.value, key.lineno)
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    ]


ENGINE_FILES = _python_files(ENGINE)
SRC_FILES = _python_files(SRC)


def _id(path: Path) -> str:
    return _rel(path)


def _id_any(item: object) -> str:
    """Test id for a mixed ``(path, function)`` parametrisation.

    pytest calls this once per argument, so a case reads as
    ``engine/gates/toehold.py-evaluate_design`` — the file and the function that failed,
    with no need to open the test to find out which one it was.
    """
    if isinstance(item, Path):
        return _rel(item)
    return getattr(item, "name", str(item))


def test_the_engine_tree_is_where_we_think_it_is():
    """A guard on every other test here: an empty scan passes vacuously."""
    assert ENGINE.is_dir(), "src/engine/ is missing — every rule below is checking nothing"
    assert len(ENGINE_FILES) > 20, (
        f"Only {len(ENGINE_FILES)} engine files found. If the layout moved, these checks "
        "are silently passing over an empty set and enforcing nothing."
    )
    for adapter in FOLDING_ADAPTERS:
        assert (SRC / adapter).is_file(), (
            f"{adapter} is gone. It is one of the two modules allowed to fold RNA; "
            "if folding moved, rule 1 below now points at nothing."
        )


# ---------------------------------------------------------------------------
# Rule 1 — only two modules may import a folding library
# ---------------------------------------------------------------------------


def _rna_importing_files() -> dict[str, list[tuple[str, int]]]:
    found: dict[str, list[tuple[str, int]]] = {}
    for path in ENGINE_FILES:
        hits = [
            (module, lineno)
            for module, lineno in _imported_modules(path)
            if _root_of(module) in FOLDING_LIBRARIES
        ]
        if hits:
            found[_rel(path)] = hits
    return found


def test_only_the_two_folding_adapters_import_a_folding_library():
    """No third module may fold RNA (docs/ROADMAP.md E1, docs/engine.md §3.3).

    A third importer means a third set of folding parameters. Two designs folded at
    different temperatures, or under different model settings, produce free energies that
    ``engine.scoring`` will normalise onto the same axis as though they were comparable.
    The ranking is then wrong, every number in it looks reasonable, and nothing in the
    system can detect it. It also means the ViennaRNA version recorded on the run no
    longer describes how every number was produced, so the run is not reproducible.

    If a gate family needs to fold something, add a method to ``FoldEngine`` and call it.
    """
    offenders = {
        relpath: hits
        for relpath, hits in _rna_importing_files().items()
        if relpath not in FOLDING_ADAPTERS
    }
    listed = "\n  ".join(
        f"{relpath}:{lineno} imports '{module}'"
        for relpath, hits in sorted(offenders.items())
        for module, lineno in hits
    )
    assert not offenders, (
        "A module outside the two folding adapters imported a folding library:\n  "
        + listed
        + "\n\nOnly these may fold:\n  "
        + "\n  ".join(FOLDING_ADAPTERS)
        + "\n\nEvery other module asks FoldEngine or FoldProfiler. One folding "
        "temperature per run, one recorded library version, one cache."
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "docs/ROADMAP.md E1 rung 4: stages/folding.py is still a stub — its "
        "RNAplfold body (and therefore its `import RNA`) lands in Step 5. This "
        "xfail is the reminder; delete the marker when FoldProfiler.profile is real."
    ),
)
def test_both_folding_adapters_actually_fold():
    """The other half of rule 1: each declared adapter really is the folding front door.

    An adapter that imports no folding library is either dead code or, worse, a class
    whose ``profile()`` returns numbers that came from somewhere else. If ``FoldProfiler``
    stops folding, every trigger in the run is selected on an accessibility value that no
    RNA structure model produced, and the switches are built against sequences that are in
    reality buried in a hairpin.
    """
    importers = set(_rna_importing_files())
    missing = [adapter for adapter in FOLDING_ADAPTERS if adapter not in importers]
    assert not missing, (
        "These modules are declared folding adapters but import no folding library:\n  "
        + "\n  ".join(missing)
        + "\n\nEither they are unimplemented (expected before Step 5) or they are "
        "returning structure numbers that no folding model produced."
    )


# ---------------------------------------------------------------------------
# Rule 2 — nobody touches the process-global folding temperature
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", SRC_FILES, ids=_id)
def test_no_module_touches_the_global_folding_temperature(path: Path):
    """``RNA.cvar`` is forbidden everywhere (src/engine/gates/tools/folding.py:84-90).

    ``RNA.cvar.temperature`` is process-global. Setting it in one place changes the
    temperature of every fold that happens afterwards anywhere in the process — including
    folds that were already queued, and including other jobs once folding moves to a
    process pool. The result is a run whose designs were folded at two different
    temperatures with no record of which was which, and free energies that cannot be
    compared to each other or to the previous run.

    Model parameters travel explicitly on an ``RNA.md()`` handed to the fold compound.
    """
    tree = _parse(path)
    violations = [
        f"{_rel(path)}:{node.lineno} uses RNA.cvar"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "cvar"
        and isinstance(node.value, ast.Name)
        and node.value.id in ("RNA", "ViennaRNA")
    ]
    violations += [
        f"{_rel(path)}:{node.lineno} imports cvar from {node.module}"
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module in FOLDING_LIBRARIES
        and any(alias.name == "cvar" for alias in node.names)
    ]
    assert not violations, (
        "Process-global folding state was modified:\n  "
        + "\n  ".join(violations)
        + "\n\nPass model parameters explicitly (RNA.md()) to the fold compound. A "
        "global temperature silently changes every later fold in the process, so half "
        "a run can be folded at one temperature and half at another with no record."
    )


# ---------------------------------------------------------------------------
# Rule 3 — shared tools are constructed exactly once, in build_tools()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [p for p in ENGINE_FILES if _rel(p) != TOOL_FACTORY], ids=_id)
def test_shared_tools_are_constructed_only_in_the_pipeline(path: Path):
    """Only ``pipeline.build_tools()`` may construct a shared tool (docs/engine.md §2.4).

    Each of these tools carries the configuration that decides what its numbers *mean*:
    ``FoldEngine`` its folding temperature and cache, ``OffTargetScanner`` its
    transcriptome build and mismatch tolerance, ``CodonOptimizer`` its codon table.

    A second instance produces a second set of numbers under a second configuration, and
    they land in the same ranking as if they were the same measurement. An off-target
    penalty computed against a different transcriptome build looks exactly like one
    computed against the right build — plausible, precise, and meaningless. The cold cache
    is the least of it.

    Tools are built once in ``build_tools()`` and passed down. If a class needs one, it
    takes it as a constructor argument.
    """
    violations = [
        f"{_rel(path)}:{lineno} constructs {name}()"
        for name, lineno in _called_names(_parse(path))
        if name in SHARED_TOOLS
    ]
    assert not violations, (
        "A shared tool was constructed outside pipeline.build_tools():\n  "
        + "\n  ".join(violations)
        + f"\n\nConstruct these once per run in {TOOL_FACTORY} and pass the instance "
        "down: " + ", ".join(SHARED_TOOLS) + ".\nTwo instances mean two configurations "
        "producing numbers that get ranked against each other as though they were "
        "measured the same way."
    )


# ---------------------------------------------------------------------------
# Rule 4 — gate families measure, they do not score
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _python_files(ENGINE / "gates"), ids=_id)
def test_gate_families_never_import_scoring(path: Path):
    """Nothing under ``gates/`` may import ``engine.scoring`` (src/engine/gates/base.py:79-85).

    A gate family returns **raw** measurements. Normalisation, weighting, hard filters and
    ranking happen once, in ``engine.scoring``, against the profile recorded on the run.

    A family that normalises its own numbers has put its designs on a different axis from
    every other family's, so a toehold and an antisense construct can no longer be
    compared — and the comparison still runs, still produces a ranked list, and still
    tells the team which construct to order. It is also unauditable after the fact,
    because the recorded profile no longer describes how the score was produced.
    """
    violations = [
        f"{_rel(path)}:{lineno} imports '{module}'"
        for module, lineno in _imported_modules(path)
        if module == "engine.scoring" or module.startswith("engine.scoring.")
    ]
    assert not violations, (
        "A gate family imported the scoring layer:\n  "
        + "\n  ".join(violations)
        + "\n\nReturn raw measurements keyed by metric name and stop there. Weighting "
        "and filtering belong to engine.scoring, which is the only place that knows how "
        "to put two different chemistries on one axis."
    )


# ---------------------------------------------------------------------------
# Rule 5 — gate families do not reach for stage tools
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _python_files(ENGINE / "gates"), ids=_id)
def test_gate_families_do_not_use_stage_tools(path: Path):
    """``FoldProfiler`` and ``OffTargetScanner`` must not be *used* under ``gates/``.

    Both belong to stage 2. By the time a gate family sees a ``TriggerCandidate``, its
    accessibility, openness and off-target penalty have already been measured and stored
    on the record. Re-measuring them inside the family produces a second number for the
    same physical quantity, computed with whatever window or mismatch settings the family
    chose — and only one of the two reaches the report, with nothing indicating which.

    ``TriggerCandidate.accessibility`` is a value to read, not a value to recompute.

    Mentioning these classes in prose is fine and common in this codebase; this check
    looks at code only, so a docstring that warns you about them does not trip it.
    """
    violations = [
        f"{_rel(path)}:{lineno} references {name}"
        for name, lineno in _referenced_names(_parse(path))
        if name in STAGE_ONLY_TOOLS
    ]
    assert not violations, (
        "A gate family reached for a stage-2 tool:\n  "
        + "\n  ".join(violations)
        + "\n\nStage 2 already measured accessibility and off-target risk and stored "
        "them on the trigger. Read the field. Recomputing gives two different numbers "
        "for one quantity and no way to tell which one was reported."
    )


# ---------------------------------------------------------------------------
# Rule 6 — a metric that could not be measured is None, never a magic number
# ---------------------------------------------------------------------------


def _measuring_functions() -> list[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef]]:
    out = []
    for path in ENGINE_FILES:
        for func in _functions(_parse(path)):
            if func.name in MEASURING_FUNCTIONS:
                out.append((path, func))
    return out


@pytest.mark.parametrize(
    ("path", "func"),
    _measuring_functions(),
    ids=_id_any,
)
def test_measuring_functions_never_return_a_sentinel(
    path: Path, func: ast.FunctionDef | ast.AsyncFunctionDef
):
    """A failed measurement is ``None``. It is never ``0``, ``-1``, ``999`` or ``NaN``.

    ``normalize_value`` has no way to tell a sentinel from a measurement. Feed it ``0.0``
    for ``predicted_leakage`` and it normalises to a **perfect** score on a
    lower-is-better metric — and ``0.0`` also clears the ``predicted_leakage <= 0.85``
    hard filter. So the one design whose leakage could not be computed becomes the design
    that outranks every correctly-measured candidate, and it is the one the team orders.

    ``None`` is handled explicitly by ``MetricSpec.missing_behavior``, which treats a
    missing value as the worst case instead of the best.

    Two patterns are flagged, both deliberately narrow so a hit is always real:
      * a numeric ``return`` inside an ``except`` handler (or a returned dict containing
        one) — the "folding blew up, return zero" reflex;
      * ``.get("<metric name>", 0)`` — a default that silently invents a measurement.
    """
    relpath = _rel(path)
    violations: list[str] = []

    for handler in [n for n in ast.walk(func) if isinstance(n, ast.ExceptHandler)]:
        for node in ast.walk(handler):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            if _is_sentinel_number(node.value):
                violations.append(
                    f"{relpath}:{node.lineno} returns {ast.unparse(node.value)} "
                    f"from an except handler in {func.name}()"
                )
            elif isinstance(node.value, ast.Dict):
                for key, value in zip(node.value.keys, node.value.values, strict=True):
                    if _is_sentinel_number(value):
                        label = (
                            key.value
                            if isinstance(key, ast.Constant) and isinstance(key.value, str)
                            else "<computed key>"
                        )
                        violations.append(
                            f"{relpath}:{node.lineno} returns "
                            f"{label}={ast.unparse(value)} from an except handler "
                            f"in {func.name}()"
                        )

    metric_names = _declared_metric_names()
    for node in ast.walk(func):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "get" or len(node.args) != 2:
            continue
        key, default = node.args
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            continue
        if key.value in metric_names and _is_sentinel_number(default):
            violations.append(
                f"{relpath}:{node.lineno} defaults metric '{key.value}' to "
                f"{ast.unparse(default)} in {func.name}()"
            )

    assert not violations, (
        "A measurement that failed was reported as a number:\n  "
        + "\n  ".join(violations)
        + "\n\nReturn None for a metric you could not compute. A 0.0 for "
        "predicted_leakage normalises to a PERFECT score and clears the hard filter, so "
        "the design nobody could measure outranks the ones that were measured properly. "
        "None is scored as the worst case, which is the honest answer."
    )


# ---------------------------------------------------------------------------
# Rule 7 — records are frozen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relpath", FROZEN_RECORD_MODULES)
def test_records_are_frozen_and_slotted(relpath: str):
    """Every ``@dataclass`` in ``domain.py`` and ``contract.py`` is ``frozen``+``slots``.

    These records are the only things that travel between stages, and stages run
    concurrently. A mutable record means stage 4 can change a value stage 3 already used,
    so the design in the report is not the design that was scored — and re-running the
    same job with the same seed no longer reproduces the same output, which is what makes
    a result citable.

    ``slots=True`` is not a micro-optimisation here: without it, a typo like
    ``design.accessibilty = 0.9`` creates a new attribute instead of raising, and the real
    field keeps its old value forever.

    ``frozen=True`` is also what stops these records growing into a mutable ``RunContext``
    that every stage writes to — the god object docs/engine.md §2.3 exists to prevent.
    """
    path = SRC / relpath
    violations: list[str] = []

    for node in ast.walk(_parse(path)):
        if not isinstance(node, ast.ClassDef):
            continue
        for decorator in node.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            name = decorator.func if call else decorator
            label = getattr(name, "id", getattr(name, "attr", ""))
            if label != "dataclass":
                continue
            kwargs = {
                kw.arg: kw.value for kw in (call.keywords if call else []) if kw.arg is not None
            }
            missing = [
                flag
                for flag in ("frozen", "slots")
                if not (isinstance(kwargs.get(flag), ast.Constant) and kwargs[flag].value is True)
            ]
            if missing:
                violations.append(
                    f"{relpath}:{node.lineno} {node.name} is missing "
                    + " and ".join(f"{flag}=True" for flag in missing)
                )

    assert not violations, (
        "A record that crosses a stage boundary is mutable:\n  "
        + "\n  ".join(violations)
        + "\n\nUse @dataclass(frozen=True, slots=True). A record another stage can "
        "change is a record whose reported value may not be the value that was scored, "
        "and it breaks the promise that the same seed reproduces the same run."
    )


# ---------------------------------------------------------------------------
# Rule 8 — imports point downward only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", [p for p in ENGINE_FILES if _layer_rank(_rel(p)) is not None], ids=_id
)
def test_intra_engine_imports_point_downward(path: Path):
    """pipeline → stages → gates → gates/tools → sequences → domain, and never back.

    An upward import is the moment a layer starts needing to know who called it. A tool
    that imports a stage cannot be tested without that stage; a gate family that imports
    the pipeline cannot be run without the whole run around it. The practical cost is that
    nobody can write a small test for the science, so the science stops being tested — and
    for this project, the science *is* the product.

    Sideways imports within a layer are fine (``registry`` importing the families,
    ``binding`` importing ``folding``). One exception is called out explicitly: three
    modules under ``stages/`` are tools that live beside the stages because no gate family
    uses them, and sibling stages may import those three and only those three.
    """
    relpath = _rel(path)
    source_rank = _layer_rank(relpath)
    assert source_rank is not None  # guaranteed by the parametrisation filter

    violations: list[str] = []
    for module, lineno in _imported_modules(path):
        if _root_of(module) != "engine":
            continue
        target_relpath = _module_to_relpath(module)
        target_rank = _layer_rank(target_relpath)
        if target_rank is None:
            continue  # contract/errors/artifacts/store/scoring — see _layer_rank()
        if target_rank > source_rank:
            violations.append(
                f"{relpath}:{lineno} imports '{module}' "
                f"(layer {target_rank} from layer {source_rank} — upward)"
            )
        elif (
            target_rank == source_rank == 4
            and target_relpath != relpath
            and module not in STAGE_TOOL_MODULES
        ):
            violations.append(
                f"{relpath}:{lineno} imports sibling stage '{module}' "
                f"(only {', '.join(sorted(STAGE_TOOL_MODULES))} may be shared sideways)"
            )

    assert not violations, (
        "An import points the wrong way:\n  "
        + "\n  ".join(violations)
        + "\n\nThe order is pipeline → stages → gates → gates/tools → sequences → "
        "domain. A layer that imports upward can no longer be run — or tested — on its "
        "own, and a piece of science nobody can test in isolation is a piece of science "
        "nobody tests."
    )


# ---------------------------------------------------------------------------
# Rule 9 — the metric vocabulary is closed
# ---------------------------------------------------------------------------


def test_the_scoring_profile_declares_metrics_at_all():
    """Guards rule 9: an empty vocabulary would make the subset check vacuous."""
    names = _declared_metric_names()
    assert len(names) >= 5, (
        f"Only {len(names)} MetricSpec names parsed out of "
        "src/engine/scoring/profiles.py. If the profile changed shape, the metric "
        f"vocabulary check below is comparing against {sorted(names)} and enforcing "
        "almost nothing."
    )


@pytest.mark.parametrize(
    ("path", "func"),
    [(p, f) for p, f in _measuring_functions() if f.name == "evaluate_design"],
    ids=_id_any,
)
def test_evaluate_design_emits_only_declared_metric_names(
    path: Path, func: ast.FunctionDef | ast.AsyncFunctionDef
):
    """A gate family may only emit metric names the active profile declares.

    This is the single most expensive mistake available in this codebase, because it is
    completely silent. ``build_metrics`` iterates the *profile*, not the returned dict:

      * A name the profile does not know — a typo, a plural, ``leakage`` instead of
        ``predicted_leakage`` — is dropped on the floor. The measurement was computed and
        then discarded.
      * The metric the profile *did* expect is now missing, so ``missing_behavior`` scores
        it as the worst possible value. The design is penalised on a metric that was
        measured correctly.

    Nothing raises. Nothing warns. The run completes, the report renders, and the ranking
    is wrong. If a family needs a new metric, add the ``MetricSpec`` to
    ``scoring/profiles.py`` in the same commit — that is the whole fix.

    The legal names are parsed out of ``profiles.py`` by AST, so this check can never
    drift from the profile it is enforcing.
    """
    declared = _declared_metric_names()
    emitted = _emitted_metric_names(func)
    unknown = sorted({name for name, _ in emitted if name not in declared})
    lines = [
        f"{_rel(path)}:{lineno} emits '{name}'" for name, lineno in emitted if name not in declared
    ]
    assert not unknown, (
        f"{_rel(path)}::{func.name} emits metric names the scoring profile does not "
        "declare:\n  "
        + "\n  ".join(lines)
        + "\n\nDeclared in src/engine/scoring/profiles.py:\n  "
        + ", ".join(sorted(declared))
        + "\n\nAn undeclared name is silently discarded, AND the metric the profile "
        "expected is then treated as missing and scored as the worst possible value. "
        "The design is punished for a measurement that was computed correctly, and "
        "nothing anywhere reports that this happened. Add the MetricSpec in the same "
        "commit as the metric."
    )


# ---------------------------------------------------------------------------
# Rule 10 — every stub says what is missing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ENGINE_FILES, ids=_id)
def test_every_stub_carries_a_message(path: Path):
    """Every ``raise NotImplementedError`` carries a non-empty message.

    Roughly a third of this engine is still stubs, and the message is how the remaining
    work stays findable: ``grep -rn "NotImplementedError" src/engine/`` is the real
    to-do list, and the convention here is ``NotImplementedError("Step 5 — …")``.

    A bare ``raise NotImplementedError`` also produces a traceback that names a line
    number and nothing else. A biologist who hits it mid-run learns that something is
    unimplemented but not what, not which stage, and not whether their input caused it.
    """
    violations: list[str] = []
    for node in ast.walk(_parse(path)):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        exc = node.exc
        if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
            violations.append(f"{_rel(path)}:{node.lineno} raises a bare NotImplementedError")
            continue
        if not (
            isinstance(exc, ast.Call)
            and isinstance(exc.func, ast.Name)
            and exc.func.id == "NotImplementedError"
        ):
            continue
        first = exc.args[0] if exc.args else None
        has_message = (
            isinstance(first, ast.Constant)
            and isinstance(first.value, str)
            and bool(first.value.strip())
        ) or (first is not None and isinstance(first, ast.JoinedStr))
        if not has_message:
            violations.append(
                f"{_rel(path)}:{node.lineno} raises NotImplementedError with no message"
            )

    assert not violations, (
        "A stub does not say what is missing:\n  "
        + "\n  ".join(violations)
        + '\n\nWrite NotImplementedError("Step 5 — what this owes its caller"). The '
        "message is what makes the remaining work greppable, and it is the only thing a "
        "researcher who hits this mid-run has to go on."
    )
