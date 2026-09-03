"""Generate ``docs/api-surface.md`` — the inventory of everything the engine already has.

Why this exists
---------------
Seven people are folding seven separately vibe-coded modules into one repository. The
expensive failure is not a merge conflict; it is a member writing ``def gc_content(seq)``
for the fourth time, on a different scale, and every downstream metric quietly shifting.
A human index would be stale within a week, so the index is generated from the source and
a test fails when the two disagree.

How it works
------------
Pure ``ast``. This script **never imports the code it documents**, which is the whole
point: it runs in a checkout with no Django, no ViennaRNA, no pytest and no virtualenv,
so a member who cannot yet run the test suite can still regenerate the doc.

Signatures are reconstructed by walking ``posonlyargs / args / defaults / vararg /
kwonlyargs / kw_defaults / kwarg`` and ``ast.unparse``-ing every annotation and default —
never by a regex over the source, and never by ``inspect.signature``, which would need an
import and would flatten ``from __future__ import annotations`` strings.

Definitions this script commits to
----------------------------------
* **public** = the name does not start with ``_``. Nothing in ``src/engine`` declares
  ``__all__``, so the underscore convention is the only rule available. ``__init__`` is
  the one dunder kept: it is the dependency-injection contract, and "which tools does
  this class need?" is exactly what a contributor comes here to find out.
* **STUB** — the body raises ``NotImplementedError`` (the engine's own convention is
  ``raise NotImplementedError("Step 5 — ...")``). Not written yet; claim it.
* **ABSTRACT** — decorated ``@abstractmethod``. A contract for subclasses, not a gap.
  ``GateFamily``'s five abstract methods have docstring-only bodies, so a plain
  "raises NotImplementedError" test would miscount them as done.
* **PROTOCOL** — the body is ``...`` (``EngineClient``). A shape, never called.
* **BUILT** — anything else. **Call it, do not rewrite it.**

Deliberately no line numbers
----------------------------
Line numbers would make the generated file churn on every unrelated edit, ``--check``
would fail constantly, and contributors would learn to ignore it. The module's file path
is printed once per section instead, so the doc only changes when the API changes.

Usage
-----
    uv run python tools/gen_api_surface.py            # rewrite docs/api-surface.md
    uv run python tools/gen_api_surface.py --check    # exit 1 if it is stale
    uv run python tools/gen_api_surface.py --stdout   # print, write nothing

``uv run`` is not required — ``python tools/gen_api_surface.py`` works too, because this
script imports nothing but the standard library.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / "src" / "engine"
SRC_DIR = REPO_ROOT / "src"
OUTPUT_PATH = REPO_ROOT / "docs" / "api-surface.md"

#: How to regenerate, quoted verbatim in the file header and in the staleness test.
REGEN_COMMAND = "uv run python tools/gen_api_surface.py"

#: Truncation for a constant's rendered value. ``CODON_TABLE`` is 64 entries long and
#: nobody reads it here; they read that it exists so they do not retype it.
MAX_CONST_VALUE = 88

#: Summary-line budget in a table cell. Past this, the purpose is cut at a sentence end.
MAX_PURPOSE = 240

#: The engine tags its shared functions with the design map's S-numbers, e.g.
#: ``"""S3 — trigger/switch hybridisation energy."""``. Surfacing the tag lets a member
#: holding the pipeline spec jump straight from "S7" to the class that implements it.
#:
#: Anchored to the START of the docstring on purpose. Every real tag in this codebase
#: sits there, immediately before an em dash (verified: `grep -rn '"""S[0-9]' src/engine/`
#: — every hit matches this shape). A docstring is free to *discuss* another S-number in
#: its prose without claiming it — e.g. gates/tools/folding.py's module doc explains that
#: S1 lives in stages/folding.py instead — and an unanchored scan over the whole text
#: would misread that explanation as a claim. `engine.gates.tools`'s own package
#: docstring lists what does NOT live there for exactly this reason; it must not end up
#: tagged S1 through S9.
S_NUMBER_RE = re.compile(r"^\s*(S\d{1,2}(?:\s*,\s*S\d{1,2})*)\s*[—-]")

STATUS_STUB = "STUB"
STATUS_BUILT = "BUILT"
STATUS_ABSTRACT = "ABSTRACT"
STATUS_PROTOCOL = "PROTOCOL"

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


# --------------------------------------------------------------------------------------
# Layers. Printed in dependency order, because the answer to "may I call this?" is
# "only if it is above you in this list" (docs/architecture.md; imports point downward).
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Layer:
    """One section of the generated document."""

    key: str
    title: str
    blurb: str
    prefixes: tuple[str, ...] = ()
    exact: tuple[str, ...] = ()

    def matches(self, module: str) -> bool:
        return module in self.exact or any(
            module == p or module.startswith(p + ".") for p in self.prefixes
        )


LAYERS: tuple[Layer, ...] = (
    Layer(
        key="domain",
        title="Layer 1 · Domain — the vocabulary",
        blurb=(
            "Data and arithmetic only, no science. Every value that crosses a module "
            "boundary must already be one of these types. Collections are **tuples**, "
            "not lists, because the dataclasses are `frozen=True, slots=True`."
        ),
        exact=("engine.domain",),
    ),
    Layer(
        key="sequences",
        title="Layer 2 · Sequences — S6, the most-reinvented module in the repo",
        blurb=(
            "Pure functions over nucleotide strings: no state, no dependencies, all "
            "BUILT. If you are about to write a reverse-complement, a GC%, a codon "
            "split, a translation or a sliding window, it is already here. Note "
            "`gc_content` returns **percent (0-100)**, not a fraction."
        ),
        exact=("engine.sequences",),
    ),
    Layer(
        key="scoring",
        title="Layer 3 · Scoring — the single ranking authority",
        blurb=(
            "The metric vocabulary lives in `DEFAULT_V1` and nowhere else. "
            "`GateFamily.evaluate_design` must return **raw** values keyed by exactly "
            "those metric names; a name that is not in the profile is silently dropped "
            "and the candidate is scored as if the metric were missing, which is "
            "`missing_behavior='worst'`. No module may normalise or weight on its own."
        ),
        prefixes=("engine.scoring",),
    ),
    Layer(
        key="gate_tools",
        title="Layer 4 · Gate tools — the scientific primitives",
        blurb=(
            "Constructed once per run by `engine.pipeline.build_tools` and injected. "
            "`engine.gates.tools.folding` is one of only two modules in the engine "
            "permitted to `import RNA`; everything else folds through a `FoldEngine` "
            "instance it was handed, so the cache and the temperature stay shared."
        ),
        prefixes=("engine.gates.tools",),
    ),
    Layer(
        key="gates",
        title="Layer 5 · Gate families — where a switch chemistry goes",
        blurb=(
            "`GateFamily` is the one real class hierarchy in the engine. A ported gate "
            "module becomes a subclass here: set the ClassVars, implement the five "
            "methods, add one `register(...)` line. Nothing else in the codebase or the "
            "frontend needs to change."
        ),
        prefixes=("engine.gates",),
    ),
    Layer(
        key="stages",
        title="Layer 6 · Stages — the six steps of a run",
        blurb=(
            "Stages hold configuration, never accumulated state. Each takes its tools "
            "by constructor injection and calls them; a stage that folds, scans or "
            "screens by itself has re-forked a rule that exists to be shared."
        ),
        prefixes=("engine.stages",),
    ),
    Layer(
        key="top",
        title="Layer 7 · Top level — contract, errors, composition",
        blurb=(
            "`engine.contract` and `engine.client` are the **only** modules Platform "
            "code may import. `engine.pipeline` is the single assembly point: tools are "
            "constructed there once and passed down."
        ),
    ),
)


def layer_of(module: str) -> Layer:
    """First matching layer wins, so `engine.gates.tools` lands before `engine.gates`."""
    for layer in LAYERS:
        if layer.matches(module):
            return layer
    return LAYERS[-1]


# --------------------------------------------------------------------------------------
# AST extraction
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Symbol:
    """A function or a method."""

    name: str
    signature: str
    status: str
    purpose: str
    s_number: str
    decorators: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Attribute:
    """A dataclass field, a ClassVar or a plain class-level assignment."""

    name: str
    type_: str
    default: str


@dataclass(frozen=True, slots=True)
class Constant:
    """A public module-level assignment."""

    name: str
    type_: str
    value: str


@dataclass(slots=True)
class Class:
    """A public class."""

    name: str
    bases: tuple[str, ...]
    decorators: tuple[str, ...]
    purpose: str
    s_number: str
    attributes: list[Attribute] = field(default_factory=list)
    methods: list[Symbol] = field(default_factory=list)

    @property
    def header(self) -> str:
        base = f"({', '.join(self.bases)})" if self.bases else ""
        return f"class {self.name}{base}"


@dataclass(slots=True)
class Module:
    """One ``.py`` file under ``src/engine``."""

    name: str
    path: str
    purpose: str
    s_number: str
    constants: list[Constant] = field(default_factory=list)
    functions: list[Symbol] = field(default_factory=list)
    classes: list[Class] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.constants or self.functions or self.classes)


def purpose(docstring: str | None) -> str:
    """The summary line: the docstring's first paragraph, collapsed onto one line.

    The first *line* is not enough — the codebase wraps its summaries at 100 columns, so
    a line-based reader would print "Cheap checks only — expensive" and stop mid-sentence.
    A whole paragraph occasionally runs long, and then it is cut at a sentence boundary.
    """
    if not docstring:
        return ""
    paragraph: list[str] = []
    for line in docstring.strip().splitlines():
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    text = " ".join(" ".join(paragraph).split())
    if len(text) <= MAX_PURPOSE:
        return text
    for match in re.finditer(r"(?<=[.?!])\s", text):
        if match.start() >= MAX_PURPOSE // 3:
            return text[: match.start()]
    return text[: MAX_PURPOSE - 1].rstrip() + "…"


def s_number(docstring: str | None) -> str:
    """The docstring's leading S-tag, e.g. ``S10, S12``, or an empty string.

    Only the tag *before the docstring's own em dash* counts — see ``S_NUMBER_RE``.
    """
    if not docstring:
        return ""
    match = S_NUMBER_RE.match(docstring)
    if not match:
        return ""
    hits = sorted({n for n in re.findall(r"\d{1,2}", match.group(1))}, key=int)
    return ", ".join("S" + h for h in hits)


def decorator_names(node: ast.ClassDef | FunctionNode) -> tuple[str, ...]:
    return tuple("@" + ast.unparse(d) for d in node.decorator_list)


def render_signature(node: FunctionNode) -> str:
    """Rebuild the source-level signature, every argument form included."""
    args = node.args
    parts: list[str] = []

    def render_arg(arg: ast.arg) -> str:
        rendered = arg.arg
        if arg.annotation is not None:
            rendered += ": " + ast.unparse(arg.annotation)
        return rendered

    positional = list(args.posonlyargs) + list(args.args)
    defaults = list(args.defaults)
    first_defaulted = len(positional) - len(defaults)

    for index, arg in enumerate(positional):
        rendered = render_arg(arg)
        if index >= first_defaulted:
            rendered += " = " + ast.unparse(defaults[index - first_defaulted])
        parts.append(rendered)
        if args.posonlyargs and index == len(args.posonlyargs) - 1:
            parts.append("/")

    if args.vararg is not None:
        parts.append("*" + render_arg(args.vararg))
    elif args.kwonlyargs:
        # A bare ``*`` — the keyword-only marker. In this codebase it is load-bearing:
        # ``write_artifact(..., *, kind, media_type)`` cannot be called positionally.
        parts.append("*")

    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        rendered = render_arg(arg)
        if default is not None:
            rendered += " = " + ast.unparse(default)
        parts.append(rendered)

    if args.kwarg is not None:
        parts.append("**" + render_arg(args.kwarg))

    returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
    keyword = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{keyword} {node.name}({', '.join(parts)}){returns}"


def raises_not_implemented(node: FunctionNode) -> bool:
    """Does this body raise ``NotImplementedError`` anywhere inside itself?"""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Raise):
            continue
        exc = sub.exc
        name = None
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            name = exc.func.id
        elif isinstance(exc, ast.Name):
            name = exc.id
        if name == "NotImplementedError":
            return True
    return False


def has_ellipsis_body(node: FunctionNode) -> bool:
    """Is the body just ``...`` (after an optional docstring)? That is a Protocol."""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            body = body[1:]
    return len(body) == 1 and (
        isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and body[0].value.value is Ellipsis
    )


def status_of(node: FunctionNode, decorators: tuple[str, ...]) -> str:
    """ABSTRACT and PROTOCOL are contracts; STUB is unclaimed work; BUILT is callable.

    ``@abstractmethod`` wins over a ``NotImplementedError`` body: an abstract method that
    also raises is still a contract, and ``ABCMeta`` blocks the incomplete subclass long
    before anyone can call it.
    """
    if any(d.endswith("abstractmethod") for d in decorators):
        return STATUS_ABSTRACT
    if raises_not_implemented(node):
        return STATUS_STUB
    if has_ellipsis_body(node):
        return STATUS_PROTOCOL
    return STATUS_BUILT


def is_public(name: str) -> bool:
    """``__init__`` is kept on purpose — it is the dependency-injection contract."""
    return not name.startswith("_") or name == "__init__"


def build_symbol(node: FunctionNode) -> Symbol:
    decorators = decorator_names(node)
    doc = ast.get_docstring(node)
    return Symbol(
        name=node.name,
        signature=render_signature(node),
        status=status_of(node, decorators),
        purpose=purpose(doc),
        s_number=s_number(doc),
        decorators=decorators,
    )


def truncate(text: str, limit: int = MAX_CONST_VALUE) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1].rstrip() + "…"


def parse_module(path: Path) -> Module:
    """Extract the public surface of one file, without importing it."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    doc = ast.get_docstring(tree)

    relative = path.relative_to(REPO_ROOT).as_posix()
    dotted = path.relative_to(SRC_DIR).with_suffix("").as_posix().replace("/", ".")
    if dotted.endswith(".__init__"):
        dotted = dotted[: -len(".__init__")]

    module = Module(
        name=dotted,
        path=relative,
        purpose=purpose(doc),
        s_number=s_number(doc),
    )

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and is_public(target.id):
                    module.constants.append(
                        Constant(target.id, "", truncate(ast.unparse(node.value)))
                    )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if is_public(node.target.id):
                module.constants.append(
                    Constant(
                        node.target.id,
                        ast.unparse(node.annotation),
                        truncate(ast.unparse(node.value)) if node.value else "",
                    )
                )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if is_public(node.name):
                module.functions.append(build_symbol(node))
        elif isinstance(node, ast.ClassDef):
            if is_public(node.name):
                module.classes.append(parse_class(node))

    return module


def parse_class(node: ast.ClassDef) -> Class:
    doc = ast.get_docstring(node)
    cls = Class(
        name=node.name,
        bases=tuple(ast.unparse(b) for b in node.bases)
        + tuple(ast.unparse(k) for k in node.keywords),
        decorators=decorator_names(node),
        purpose=purpose(doc),
        s_number=s_number(doc),
    )

    for sub in node.body:
        if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
            if is_public(sub.name):
                cls.methods.append(build_symbol(sub))
        elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
            if is_public(sub.target.id):
                cls.attributes.append(
                    Attribute(
                        sub.target.id,
                        ast.unparse(sub.annotation),
                        truncate(ast.unparse(sub.value)) if sub.value else "",
                    )
                )
        elif isinstance(sub, ast.Assign):
            for target in sub.targets:
                if isinstance(target, ast.Name) and is_public(target.id):
                    cls.attributes.append(
                        Attribute(target.id, "", truncate(ast.unparse(sub.value)))
                    )

    return cls


def collect_modules(root: Path = ENGINE_DIR) -> list[Module]:
    """Every ``.py`` under ``src/engine``, ``__pycache__`` skipped, sorted by name."""
    paths = [
        p
        for p in sorted(root.rglob("*.py"))
        if "__pycache__" not in p.parts and "migrations" not in p.parts
    ]
    modules = [parse_module(p) for p in paths]
    modules.sort(key=lambda m: (m.name.count("."), m.name))
    return modules


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------


def cell(text: str) -> str:
    """Escape a table cell. `float | None` would otherwise end the column."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def code_cell(text: str) -> str:
    return f"`{cell(text)}`" if text else ""


def symbol_row(symbol: Symbol) -> str:
    prefix = " ".join(d for d in symbol.decorators if d != "@abstractmethod")
    signature = f"{prefix} {symbol.signature}".strip()
    purpose = symbol.purpose
    if symbol.s_number:
        purpose = f"**{symbol.s_number}** · {purpose}" if purpose else f"**{symbol.s_number}**"
    return f"| `{symbol.status}` | {code_cell(signature)} | {cell(purpose)} |"


def counts(modules: list[Module]) -> dict[str, int]:
    """Callable totals. ``__init__`` is counted apart, as design map 2 counted it."""
    tally = {STATUS_BUILT: 0, STATUS_STUB: 0, STATUS_ABSTRACT: 0, STATUS_PROTOCOL: 0}
    tally["__init__"] = 0
    for module in modules:
        symbols = list(module.functions)
        for cls in module.classes:
            symbols.extend(cls.methods)
        for symbol in symbols:
            if symbol.name == "__init__":
                tally["__init__"] += 1
            else:
                tally[symbol.status] += 1
    tally["callables"] = sum(
        tally[k] for k in (STATUS_BUILT, STATUS_STUB, STATUS_ABSTRACT, STATUS_PROTOCOL)
    )
    return tally


def module_counts(module: Module) -> tuple[int, int]:
    """(built-ish, stub) for one module, ``__init__`` excluded."""
    built = stub = 0
    symbols = list(module.functions)
    for cls in module.classes:
        symbols.extend(cls.methods)
    for symbol in symbols:
        if symbol.name == "__init__":
            continue
        if symbol.status == STATUS_STUB:
            stub += 1
        else:
            built += 1
    return built, stub


def render_header(modules: list[Module]) -> list[str]:
    tally = counts(modules)
    classes = sum(len(m.classes) for m in modules)
    lines = [
        "# API surface — everything the engine already has",
        "",
        "<!-- GENERATED FILE — DO NOT EDIT BY HAND. -->",
        "",
        "> **This file is generated from the source.** Do not edit it; edit the code and",
        f"> regenerate with `{REGEN_COMMAND}`.",
        "> `tests/test_api_surface_is_fresh.py` fails if the two have drifted, so it cannot",
        "> quietly go stale.",
        "",
        "## How to use this file",
        "",
        "**Search here before you write any function.** Ctrl-F the thing you were about to",
        "write — `gc_content`, `reverse_complement`, `hybridization_energy`, `mint_id`,",
        "`write_artifact` — and if it is listed as `BUILT`, call it instead. The failure this",
        "prevents is not a merge conflict; it is two members computing the same quantity on",
        "two different scales, after which `engine.scoring` normalises both onto one axis as",
        "though they were comparable, and no error is ever raised.",
        "",
        "Four statuses, and they mean different things:",
        "",
        "| Status | Meaning | What you do with it |",
        "| --- | --- | --- |",
        "| `BUILT` | Implemented and callable today. | **Call it. Never reimplement it.** |",
        '| `STUB` | Body raises `NotImplementedError("Step 5 — …")`. | Unclaimed work — '
        "this is where a ported module lands. |",
        "| `ABSTRACT` | `@abstractmethod`; a contract for subclasses. | Implement it in your "
        "subclass; `ABCMeta` refuses to instantiate you until you do. |",
        "| `PROTOCOL` | Body is `...`; a structural shape. | Match the shape. Nothing calls "
        "the `...` itself. |",
        "",
        "`__init__` is listed even though it is a dunder, because it **is** the dependency-",
        "injection contract: it tells you which tools an object must be handed. Tools are",
        "constructed once in `engine.pipeline.build_tools` and passed down — never built",
        "inside a stage or a gate.",
        "",
        "Public means the name does not start with `_`. No engine module declares `__all__`,",
        "so that convention is the only rule there is.",
        "",
        "## Totals",
        "",
        "| | Count |",
        "| --- | ---: |",
        f"| Modules | {len(modules)} |",
        f"| Public classes | {classes} |",
        f"| Public callables (excluding `__init__`) | {tally['callables']} |",
        f"| — `BUILT` | {tally[STATUS_BUILT]} |",
        f"| — `STUB` | {tally[STATUS_STUB]} |",
        f"| — `ABSTRACT` | {tally[STATUS_ABSTRACT]} |",
        f"| — `PROTOCOL` | {tally[STATUS_PROTOCOL]} |",
        f"| `__init__` constructors | {tally['__init__']} |",
        "",
    ]
    return lines


def render_index(modules: list[Module]) -> list[str]:
    lines = [
        "## Index",
        "",
        "Modules in dependency order. Imports point downward only: a layer may call the",
        "layers above it, never the ones below.",
        "",
        "| Layer | Module | S | Not `STUB` | `STUB` | Purpose |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for layer in LAYERS:
        for module in modules:
            if layer_of(module.name) is not layer:
                continue
            built, stub = module_counts(module)
            lines.append(
                f"| {layer.key} | `{module.name}` | {cell(module.s_number)} | "
                f"{built} | {stub} | {cell(module.purpose)} |"
            )
    lines.append("")
    return lines


def render_module(module: Module) -> list[str]:
    heading = f"### `{module.name}`"
    if module.s_number:
        heading += f" · {module.s_number}"
    lines = [heading, "", f"`{module.path}`"]
    if module.purpose:
        lines.append("")
        lines.append(module.purpose)
    lines.append("")

    if module.is_empty:
        # A package ``__init__`` here is either empty or policy-in-a-docstring. Neither
        # re-exports anything, which is why every import in this repo names its defining
        # module: ``from engine.gates.tools.folding import FoldEngine``, never
        # ``from engine.gates.tools import FoldEngine``.
        note = (
            "*No public symbols — the docstring is the whole file.*"
            if module.purpose
            else "*Empty file — no docstring, no public symbols, no re-exports.*"
        )
        lines += [note, ""]
        return lines

    if module.constants:
        lines += ["| Constant | Type | Value |", "| --- | --- | --- |"]
        for const in module.constants:
            lines.append(
                f"| `{cell(const.name)}` | {code_cell(const.type_)} | {code_cell(const.value)} |"
            )
        lines.append("")

    if module.functions:
        lines += ["| Status | Function | Purpose |", "| --- | --- | --- |"]
        lines += [symbol_row(s) for s in module.functions]
        lines.append("")

    for cls in module.classes:
        lines += render_class(cls)

    return lines


def render_class(cls: Class) -> list[str]:
    heading = f"#### `{cls.header}`"
    if cls.s_number:
        heading += f" · {cls.s_number}"
    lines = [heading, ""]
    if cls.decorators:
        lines += ["`" + " ".join(cls.decorators) + "`", ""]
    if cls.purpose:
        lines += [cls.purpose, ""]

    if cls.attributes:
        lines += ["| Attribute | Type | Default |", "| --- | --- | --- |"]
        for attribute in cls.attributes:
            lines.append(
                f"| `{cell(attribute.name)}` | {code_cell(attribute.type_)} "
                f"| {code_cell(attribute.default)} |"
            )
        lines.append("")

    if cls.methods:
        lines += ["| Status | Method | Purpose |", "| --- | --- | --- |"]
        lines += [symbol_row(s) for s in cls.methods]
        lines.append("")

    return lines


def render(modules: list[Module]) -> str:
    lines = render_header(modules) + render_index(modules)
    for layer in LAYERS:
        members = [m for m in modules if layer_of(m.name) is layer]
        if not members:
            continue
        lines += [f"## {layer.title}", "", layer.blurb, ""]
        for module in members:
            lines += render_module(module)
    lines += [
        "---",
        "",
        f"Generated by `tools/gen_api_surface.py` from `src/engine/`. Regenerate with "
        f"`{REGEN_COMMAND}`.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def normalise(text: str) -> str:
    """Compare on LF only. The repo is developed on Windows inside OneDrive; a CRLF
    checkout must not be reported as a stale document."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def use_utf8_console() -> None:
    """Windows consoles default to a legacy code page (cp1255 on a Hebrew Windows).

    Without this, printing a `⇄` or a `·` from the generated document dies with
    UnicodeEncodeError before the contributor ever sees the real message.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # a pipe or a capture that cannot be reconfigured
                pass


def main(argv: list[str] | None = None) -> int:
    use_utf8_console()
    parser = argparse.ArgumentParser(
        description="Generate docs/api-surface.md from src/engine/ with ast only.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write. Exit 1 if the committed file differs from a fresh generation.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the document instead of writing it.",
    )
    args = parser.parse_args(argv)

    if not ENGINE_DIR.is_dir():
        print(f"error: {ENGINE_DIR} does not exist", file=sys.stderr)
        return 2

    modules = collect_modules()
    document = render(modules)
    tally = counts(modules)
    summary = (
        f"{len(modules)} modules · {tally['callables']} public callables · "
        f"{tally[STATUS_BUILT]} BUILT · {tally[STATUS_STUB]} STUB · "
        f"{tally[STATUS_ABSTRACT]} ABSTRACT · {tally[STATUS_PROTOCOL]} PROTOCOL"
    )

    if args.stdout:
        sys.stdout.write(document)
        return 0

    if args.check:
        if not OUTPUT_PATH.exists():
            print(
                f"{OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()} is missing.\n"
                f"Regenerate it with:  {REGEN_COMMAND}",
                file=sys.stderr,
            )
            return 1
        committed = normalise(OUTPUT_PATH.read_text(encoding="utf-8"))
        if committed == normalise(document):
            print(f"docs/api-surface.md is up to date ({summary})")
            return 0
        diff = difflib.unified_diff(
            committed.splitlines(),
            normalise(document).splitlines(),
            fromfile="docs/api-surface.md (committed)",
            tofile="docs/api-surface.md (regenerated from src/engine/)",
            lineterm="",
            n=1,
        )
        print("\n".join(list(diff)[:60]), file=sys.stderr)
        print(
            "\ndocs/api-surface.md does not match src/engine/ — either the engine's public\n"
            "API changed, or the document was edited by hand. It is generated; edit the\n"
            f"code, not the document.\n\nRegenerate it and commit the result:  {REGEN_COMMAND}",
            file=sys.stderr,
        )
        return 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(document, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()} — {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
