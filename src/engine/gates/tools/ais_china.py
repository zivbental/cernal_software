"""Adapter over the AIS-China *Cutibacterium acnes* codon-optimization library.

``vendor/ais-china-codon-optimization-v2`` is a git submodule of the iGEM AIS-China team's
Apache-2.0 tool, pinned at :data:`PINNED_COMMIT`. **Their code is used unmodified**, which
is the condition of the collaboration (docs/collaborations.md): not one byte under
``vendor/`` is edited, reformatted or lint-fixed, and this module never writes there
either (bytecode writing is switched off while their package is imported). This file is the
whole of CERNAL's side of the seam: it locates the submodule, imports their package,
builds their ``ReferenceStore`` and turns their JSON report into CERNAL's conventions.

**Why a tool, and why here.** It wraps an external scientific library, exactly as
``folding.py`` wraps ViennaRNA, so it sits in ``gates/tools/`` and imports only
``engine.sequences`` and the library (CLAUDE.md §4). Stages and gate families receive it
injected; it is built once in ``pipeline.build_tools()`` (CLAUDE.md §5) — it is listed in
``SHARED_TOOLS`` of tests/engine/test_house_rules.py for that reason. Nothing builds it
yet: it is the backend ``CodonOptimizer`` will delegate to for ``Host.C_ACNES``.

**One host, deliberately.** Their ``config/defaults.json`` declares two strains. We leave
their configuration untouched, so the restriction lives here: :data:`HOST_ID` is the only
host a caller can reach — ``host_id`` is not a parameter, and ``source_host_id`` (which
would let the other strain in through the harmonization strategy) is not forwarded.

**Three traps at the boundary.** Each is measured against the pinned commit, and each is
documented again at the line of code that handles it:

1. *Their CSVs carry a UTF-8 BOM.* Read with ``utf-8-sig`` or the first column is
   named ``"\\ufeffcodon"`` and every lookup misses. Their own loader does this; we reuse
   that loader's parsed tables (:meth:`AisChinaCodons.usage_frequencies`,
   :meth:`AisChinaCodons.cai_relative_adaptiveness`) rather than parse the files a
   second time, and ``tests/engine/test_ais_china.py`` pins the BOM so a bump that drops it
   is noticed rather than assumed.
2. *Two tables, one shape, two meanings.* ``cai_weights.csv``'s ``cai_weight`` is
   **relative adaptiveness** (maximum 1.0 per synonymous family, the CAI weight ``w``).
   ``host_codon_counts.csv``'s ``sampling_probability_v1`` is **relative frequency**
   (sums to 1.0 per family), which is what ``CodonOptimizer.usage_table`` specifies.
   ``host_codon_counts.csv`` is the frequency source; ``cai_weights.csv`` is the CAI
   source. They are both 61-key ``codon -> float`` and an argmax cannot tell them apart,
   so each accessor *checks the property that defines it* and raises if it does not hold.
3. *Their reports are 1-based inclusive* (``nt_start``/``nt_end``, ``codon_position``).
   CERNAL is 0-indexed, inclusive start, exclusive end (CLAUDE.md §6). Conversion happens
   once, in :func:`_convert_edit`, which then checks ``sequence[start:end] == codon`` on
   both the original and the candidate — a round trip, not an assumption.

A fourth, smaller one: their alphabet is DNA (ACGT), CERNAL's is RNA (ACGU). Everything
crossing the seam goes through ``sequences.to_dna`` / ``sequences.to_rna``.

**Two things are deliberately left out of what this returns.** Their ``created_utc`` and
``elapsed_seconds`` are wall-clock readings; CLAUDE.md §6 keeps the wall clock out of
anything that reaches output. Their ``rna`` metric is an *opening energy of the 5' end of
the CDS* in kcal/mol — a diagnostic about their strategy, not one of the nine scored
metric names (CLAUDE.md §2), and it is reported under their name, never relabelled.

**Energy model.** Their ``codon_v2/rna.py`` does ``import RNA`` and calls
``RNA.params_load()``, which is process-global. That is not a second folding authority
only because the parameter file they load is numerically identical to ViennaRNA 2.7.2's
built-in defaults, which are what ``FoldEngine`` uses. That fact is not assumed: it is
asserted by ``tests/engine/test_ais_china_energy_model.py`` and must keep passing across
every submodule bump (CLAUDE.md §5).
"""

from __future__ import annotations

import importlib
import importlib.util
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from engine import sequences

#: The submodule's pinned commit. ``tests/engine/test_ais_china.py`` checks the checked-out
#: submodule against this, so a bump is a deliberate edit to this line, the test run, and
#: docs/collaborations.md in the same commit.
PINNED_COMMIT = "e8a57cf1b5696ed7b3931f6b63ea49afbc5ccbf9"

#: The only host this adapter exposes: *Cutibacterium acnes* ATCC 6919, RefSeq assembly
#: GCF_008728435.1. Their ``defaults.json`` also declares KPA171202; it stays unreachable.
HOST_ID = "atcc6919_GCF_008728435.1"

#: Their reference version for :data:`HOST_ID`. Recorded on every result.
REFERENCE_VERSION = "2026-09-06.v1"

#: Their strategy ids, in their canonical scheduling order.
STRATEGY_IDS: tuple[str, ...] = ("rna_start", "host_sampling", "cai_max", "tai_max", "harmonize")

#: ``<repo>/vendor/ais-china-codon-optimization-v2``. This file is
#: ``<repo>/src/engine/gates/tools/ais_china.py``.
DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "vendor" / "ais-china-codon-optimization-v2"

_STATUS_OK = "ok"


# --- Result records ---------------------------------------------------------------
#
# Frozen and slotted like every record that crosses a boundary (CLAUDE.md §6). Their
# JSON is plain dicts; these are what the rest of the engine sees.


@dataclass(frozen=True, slots=True)
class CodonEdit:
    """One synonymous codon substitution, in CERNAL coordinates.

    ``start``/``end`` are 0-indexed, inclusive start, exclusive end, so
    ``cds[start:end] == before`` and ``candidate[start:end] == after``. Their report says
    ``nt_start=3i+1, nt_end=3i+3`` (1-based inclusive); this record says ``3i, 3i+3``.
    """

    codon_index: int
    start: int
    end: int
    before: str
    after: str
    amino_acid: str


@dataclass(frozen=True, slots=True)
class AisChinaMetric:
    """One of their per-candidate measurements, in their vocabulary.

    Their names (``cai``, ``tai``, ``host_preference``, ``rna``, ``harmonization``,
    ``gc``) are **not** CERNAL's nine scored metrics and are never fed to
    ``engine.scoring``. ``value`` is ``None`` — never ``0.0`` — when they could not
    measure it, and ``reason`` then says why (CLAUDE.md §3). ``gc`` is percent 0-100;
    ``rna`` is a 5'-end opening energy in kcal/mol.
    """

    name: str
    value: float | None
    unit: str | None
    status: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class AisChinaCandidate:
    """A synonymous variant of the input CDS, RNA alphabet, with the edits that made it."""

    candidate_id: str
    sequence: str
    sequence_sha256: str
    protein: str
    metrics: tuple[AisChinaMetric, ...]
    constraints_passed: bool
    violations: tuple[str, ...]
    edits: tuple[CodonEdit, ...]
    strategies: tuple[str, ...]

    def metric(self, name: str) -> AisChinaMetric:
        """The named metric, or ``KeyError``. Never a default value."""
        for metric in self.metrics:
            if metric.name == name:
                return metric
        raise KeyError(name)


@dataclass(frozen=True, slots=True)
class StrategyOutcome:
    """What one strategy did — including that it found nothing, or could not run.

    ``status`` is theirs verbatim (``completed``, ``budget_exhausted``,
    ``no_feasible_candidate_found``, ``unavailable``, ``failed``, ``cancelled`` ...). A
    strategy that returned no sequence is reported here, never dropped silently
    (CLAUDE.md §3). ``termination_reason`` shows when a wall-clock or transition budget cut
    a search short, which is the one way a seeded run can differ across machines.
    """

    strategy_id: str
    status: str
    reason: str | None
    solver: str | None
    seed: int | None
    returned_count: int
    termination_reason: str | None


@dataclass(frozen=True, slots=True)
class AisChinaProvenance:
    """What produced the numbers: enough to say which reference and which code.

    ``implementation_sha256`` and ``consumed_file_sha256`` are (name, sha256) pairs taken
    from their own report: the hashes of the ``codon_v2/*.py`` files that ran and of the
    reference files they consumed.
    """

    host_id: str
    display_name: str
    assembly: str
    accession: str
    reference_version: str
    code_version: str
    pinned_commit: str
    implementation_sha256: tuple[tuple[str, str], ...]
    consumed_file_sha256: tuple[tuple[str, str], ...]
    coding_gc_bounds: tuple[float, float]


@dataclass(frozen=True, slots=True)
class AisChinaRun:
    """The outcome of one :meth:`AisChinaCodons.optimize` call.

    ``status`` is theirs: ``completed``, ``partial_results``, ``no_results`` or
    ``cancelled``. An empty ``candidates`` with ``status == "no_results"`` is a legitimate,
    informative answer (a CDS whose GC lies outside the host's bounds, say) and the
    reasons are in ``strategies`` and ``warnings``.
    """

    status: str
    input_sequence: str
    protein: str
    original: AisChinaCandidate
    candidates: tuple[AisChinaCandidate, ...]
    strategies: tuple[StrategyOutcome, ...]
    warnings: tuple[str, ...]
    provenance: AisChinaProvenance


# --- Loading their package --------------------------------------------------------


def _load_package(root: Path) -> ModuleType:
    """Import ``codon_v2`` from ``root`` without touching ``sys.path`` or ``vendor/``.

    Their package uses relative imports, so it is registered under its own name in
    ``sys.modules``. If something else already registered ``codon_v2`` the two must be
    the same files, otherwise we would silently run a different copy of their code than
    the one pinned.
    """
    package_dir = (root / "codon_v2").resolve()
    init = package_dir / "__init__.py"
    if not init.is_file():
        raise FileNotFoundError(
            f"{init} does not exist. The AIS-China submodule is not checked out; run "
            "`git submodule update --init vendor/ais-china-codon-optimization-v2`."
        )
    existing = sys.modules.get("codon_v2")
    if existing is not None:
        loaded_from = Path(existing.__file__).resolve().parent
        if loaded_from != package_dir:
            raise RuntimeError(
                f"codon_v2 is already imported from {loaded_from}, not from the pinned "
                f"submodule at {package_dir}."
            )
        return existing

    # Importing would otherwise leave __pycache__ directories inside vendor/.
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(
            "codon_v2", init, submodule_search_locations=[str(package_dir)]
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["codon_v2"] = module
        try:
            spec.loader.exec_module(module)
            for submodule in ("pipeline", "references", "sequence", "config"):
                importlib.import_module(f"codon_v2.{submodule}")
        except BaseException:
            for name in [n for n in sys.modules if n == "codon_v2" or n.startswith("codon_v2.")]:
                del sys.modules[name]
            raise
    finally:
        sys.dont_write_bytecode = previous
    return module


# --- The adapter ------------------------------------------------------------------


class AisChinaCodons:
    """*C. acnes* ATCC 6919 codon optimization through the AIS-China library, unmodified.

    Construct once per run (``pipeline.build_tools()``) and inject. Construction loads and
    checksum-verifies their frozen reference files; it is cheap but not free.

    Args:
        root: The directory holding their ``config/``, ``data/`` and ``codon_v2/``.
            Defaults to the pinned submodule. It is a *parameter* of their
            ``ReferenceStore``, which is the whole reason no edit to their code is needed.

    Raises:
        FileNotFoundError: The submodule is not checked out.
        RuntimeError: Their reference for :data:`HOST_ID` does not load, or reports a
            different reference version than :data:`REFERENCE_VERSION`.
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else DEFAULT_ROOT
        self._package = _load_package(self.root)
        references = importlib.import_module("codon_v2.references")
        self._pipeline = importlib.import_module("codon_v2.pipeline")
        self._sequence = importlib.import_module("codon_v2.sequence")
        self._refs = references.ReferenceStore(root=self.root)
        self._host = self._refs.get(HOST_ID)
        if self._host.manifest["reference_version"] != REFERENCE_VERSION:
            raise RuntimeError(
                f"{HOST_ID} reports reference version "
                f"{self._host.manifest['reference_version']!r}, expected {REFERENCE_VERSION!r}."
            )

    # -- reference tables -------------------------------------------------------------

    def usage_frequencies(self) -> dict[str, float]:
        """Codon -> **relative frequency** within its synonymous family, RNA keys.

        Source: ``host_codon_counts.csv``, column ``sampling_probability_v1`` — the
        frequency source, and the shape ``CodonOptimizer.usage_table`` specifies. Sums to
        1.0 within each amino acid. **Not** ``cai_weights.csv``; see
        :meth:`cai_relative_adaptiveness` for why that distinction matters.

        The file has a UTF-8 BOM; their loader reads it as ``utf-8-sig`` and we consume
        the table it parsed.

        Raises:
            RuntimeError: Their loader could not provide the table, or the table does
                not sum to 1.0 per family (it would then be some other quantity).
        """
        table = self._table("sampling")
        for amino_acid, family in self._families().items():
            total = math.fsum(table[codon] for codon in family)
            if abs(total - 1.0) > 1e-9:
                raise RuntimeError(
                    f"host_codon_counts.csv: {amino_acid} frequencies sum to {total}, not 1.0 — "
                    "this is not a relative-frequency table."
                )
        return {sequences.to_rna(codon): weight for codon, weight in table.items()}

    def cai_relative_adaptiveness(self) -> dict[str, float]:
        """Codon -> CAI weight ``w`` (**relative adaptiveness**), RNA keys.

        Source: ``cai_weights.csv``, column ``cai_weight``, computed from their 61-gene
        ribosomal reference set. ``w`` is the codon's count divided by the *largest*
        count in its family, so the best codon of every family is exactly 1.0 and the
        family does **not** sum to 1.0. Use it for CAI. For anything that wants
        probabilities (``match_codon_usage``, harmonization) use
        :meth:`usage_frequencies`; the two have the same shape and swapping them is
        invisible to an argmax and wrong everywhere else.

        Raises:
            RuntimeError: Their loader could not provide the table, or a family's maximum
                is not 1.0.
        """
        table = self._table("cai")
        for amino_acid, family in self._families().items():
            peak = max(table[codon] for codon in family)
            if abs(peak - 1.0) > 1e-9:
                raise RuntimeError(
                    f"cai_weights.csv: {amino_acid} maximum weight is {peak}, not 1.0 — "
                    "this is not a relative-adaptiveness table."
                )
        return {sequences.to_rna(codon): weight for codon, weight in table.items()}

    def _table(self, key: str) -> dict[str, float]:
        table = self._host.tables.get(key)
        if table is None:
            reason = self._host.reasons.get(key, f"{key}_reference_unavailable")
            raise RuntimeError(f"AIS-China reference table {key!r} is unavailable: {reason}")
        return table

    def _families(self) -> dict[str, tuple[str, ...]]:
        """Synonymous families as DNA codons, from their own genetic-code table 11."""
        return {aa: tuple(codons) for aa, codons in self._sequence.SYNONYMS.items()}

    # -- optimization -----------------------------------------------------------------

    def optimize(
        self,
        cds: str,
        *,
        seed: int,
        strategies: Sequence[str] | None = None,
        upstream: str = "",
        locked_codons: Sequence[int] = (),
        source_codon_counts: Mapping[str, float] | None = None,
        source_name: str = "source",
    ) -> AisChinaRun:
        """Run their pipeline on one CDS and return it in CERNAL's conventions.

        Args:
            cds: The coding sequence, RNA or DNA. Must be a whole number of codons, begin
                with a start codon for ``rna_start`` to run, and contain no internal stop.
            seed: Their reproducibility seed, 0 to 2**32 - 1. Thread ``JobRequest.seed``
                here; a given seed reproduces byte-identically and another differs.
            strategies: A subset of :data:`STRATEGY_IDS`; ``None`` means their default
                (every strategy except ``harmonize``).
            upstream: Transcribed sequence upstream of the CDS (5' UTR / RBS), for the
                ``rna_start`` opening energy. Empty means CDS-only context, which their
                report flags.
            locked_codons: **0-indexed** codon indices to keep unchanged (their API is
                1-based; converted here). The start codon and a terminal stop are always
                locked by them.
            source_codon_counts: Codon counts of the organism the CDS comes from, for the
                ``harmonize`` strategy. Keys RNA or DNA, all 61 sense codons. Without
                it ``harmonize`` is reported ``unavailable`` rather than guessed.
            source_name: Label recorded with those counts.

        Returns:
            An :class:`AisChinaRun`. A strategy that found nothing, or could not run, is
            present in ``strategies`` with its reason.

        Raises:
            ValueError: Bad input — an unknown strategy, a malformed CDS, a seed out of
                range. The message is theirs where theirs is the more precise.
            RuntimeError: Their report broke the contract this adapter relies on (a
                coordinate round trip failed, a field is missing).
        """
        unknown = sorted(set(strategies or ()) - set(STRATEGY_IDS))
        if unknown:
            raise ValueError(f"unknown strategies {unknown}; known: {list(STRATEGY_IDS)}")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"seed must be an int, got {type(seed).__name__}")

        # Their alphabet is DNA. Their own `normalize` would accept U too, but converting
        # here keeps the seam explicit and lets us compare edits against a known string.
        request: dict[str, object] = {
            "cds": sequences.to_dna(cds),
            "host_id": HOST_ID,
            "seed": seed,
            "upstream_transcribed_sequence": sequences.to_dna(upstream),
            "locked_codon_positions": [index + 1 for index in locked_codons],  # 0- to 1-based
        }
        if strategies is not None:
            request["strategies"] = list(strategies)
        if source_codon_counts is not None:
            request["source_reference"] = {
                "name": source_name,
                "counts": {sequences.to_dna(c): v for c, v in source_codon_counts.items()},
            }

        try:
            report = self._pipeline.optimize(request, refs=self._refs)
        except self._sequence.InputError as error:
            raise ValueError(f"[{error.field}] {error}") from error
        return self._convert_report(report)

    # -- report conversion --------------------------------------------------------------

    def _convert_report(self, report: dict) -> AisChinaRun:
        try:
            original_dna = report["input"]["sequence"]
            original = self._convert_candidate(report["original_result"], original_dna)
            candidates = tuple(
                self._convert_candidate(candidate, original_dna)
                for candidate in report["candidates"]
            )
            strategies = tuple(self._convert_strategy(s) for s in report["strategy_status"])
            metadata = report["reference_manifest"]
            run = report["run"]
            # `created_utc` and `elapsed_seconds` are wall-clock readings: dropped.
            provenance = AisChinaProvenance(
                host_id=metadata["host_id"],
                display_name=metadata["display_name"],
                assembly=metadata["assembly"],
                accession=metadata["accession"],
                reference_version=metadata["reference_version"],
                code_version=run["code_version"],
                pinned_commit=PINNED_COMMIT,
                implementation_sha256=tuple(sorted(run["implementation_sha256"].items())),
                consumed_file_sha256=tuple(sorted(metadata["consumed_file_sha256"].items())),
                coding_gc_bounds=(float(metadata["gc_bounds"][0]), float(metadata["gc_bounds"][1])),
            )
            return AisChinaRun(
                status=report["status"],
                input_sequence=sequences.to_rna(original_dna),
                protein=report["input"]["protein"],
                original=original,
                candidates=candidates,
                strategies=strategies,
                warnings=tuple(report["warnings"]),
                provenance=provenance,
            )
        except KeyError as missing:
            raise RuntimeError(
                f"AIS-China report is missing field {missing}; the submodule no longer "
                "matches the schema this adapter was written against."
            ) from missing

    def _convert_candidate(self, raw: dict, original_dna: str) -> AisChinaCandidate:
        sequence_dna = raw["sequence"]
        constraints = raw["constraints"]
        return AisChinaCandidate(
            candidate_id=raw["candidate_id"],
            sequence=sequences.to_rna(sequence_dna),
            sequence_sha256=raw["sequence_sha256"],
            protein=raw["protein"],
            metrics=tuple(
                _convert_metric(name, metric) for name, metric in sorted(raw["metrics"].items())
            ),
            constraints_passed=bool(constraints["passed"]),
            violations=tuple(constraints["violations"]),
            edits=tuple(_convert_edit(e, original_dna, sequence_dna) for e in raw["changes"]),
            strategies=tuple(m["strategy_id"] for m in raw["strategy_memberships"]),
        )

    @staticmethod
    def _convert_strategy(raw: dict) -> StrategyOutcome:
        budget = raw.get("budget") or {}
        seed = raw.get("seed")
        return StrategyOutcome(
            strategy_id=raw["strategy_id"],
            status=raw["status"],
            reason=raw.get("reason"),
            solver=raw.get("solver"),
            seed=int(seed) if seed is not None else None,
            returned_count=int(raw.get("returned_count", 0)),
            termination_reason=budget.get("termination_reason"),
        )


def _convert_metric(name: str, raw: dict) -> AisChinaMetric:
    """One of their ``{value, status, reason, ...}`` dicts.

    A value is kept only when their status says ``ok`` and it is a finite number; anything
    else is ``None`` (CLAUDE.md §3) with their reason attached. Never ``0.0``.
    """
    status = str(raw.get("status", "unknown"))
    value = raw.get("value")
    if status != _STATUS_OK or value is None or not math.isfinite(value):
        value = None
    return AisChinaMetric(
        name=name,
        value=float(value) if value is not None else None,
        unit=raw.get("unit"),
        status=status,
        reason=raw.get("reason"),
    )


def _convert_edit(raw: dict, original_dna: str, candidate_dna: str) -> CodonEdit:
    """Their 1-based inclusive ``nt_start``/``nt_end`` to 0-indexed half-open, verified.

    ``nt_start=3i+1, nt_end=3i+3`` becomes ``start=3i, end=3i+3``. The result is then
    checked against both sequences, because an off-by-one here would not raise: it would
    attribute an edit to the neighbouring codon (CLAUDE.md §6).
    """
    start = raw["nt_start"] - 1
    end = raw["nt_end"]
    codon_index = raw["codon_position"] - 1
    before, after = raw["before"], raw["after"]
    if not (
        end - start == 3
        and start == 3 * codon_index
        and original_dna[start:end] == before
        and candidate_dna[start:end] == after
    ):
        raise RuntimeError(
            f"AIS-China edit coordinates failed the round trip: {raw!r} does not match "
            f"original[{start}:{end}]={original_dna[start:end]!r} / "
            f"candidate[{start}:{end}]={candidate_dna[start:end]!r}."
        )
    return CodonEdit(
        codon_index=codon_index,
        start=start,
        end=end,
        before=sequences.to_rna(before),
        after=sequences.to_rna(after),
        amino_acid=raw["amino_acid"],
    )
