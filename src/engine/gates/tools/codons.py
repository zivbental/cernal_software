"""S8 — codon usage and synonymous rewriting.

Two jobs, both about the fact that a switch is fused to a protein-coding sequence and
the fusion has to work as both RNA structure and protein.

**Rewriting.** The genetic code is redundant: most amino acids have several codons. That
redundancy is design freedom — a linker or the start of a CDS can be rewritten to change
its folding without changing the protein at all. A toehold whose stem is disrupted by the
payload's first few codons can often be fixed this way rather than by redesigning the
switch.

**Scoring.** Not all synonymous codons are equal in a given host. A CDS full of codons
*E. coli* rarely uses translates slowly and expresses poorly, however good the switch is.

**Where the work is done.** Scoring is in-repo and pure (``translation_score``: a
geometric-mean CAI off the host's codon-usage table, no third-party call). Rewriting for
*evolutionary stability* — replication slippage, recombination-mediated deletion — is
delegated to ESO (``evolutionary-stability-optimizer``, which drives DNAChisel). **This is
the only module in ``src/engine`` that may import ``eso`` or ``dnachisel``**
(``tests/engine/test_house_rules.py``): DNAChisel ships its own structure heuristics
(``AvoidHairpins``) and would become a second folding authority beside ``FoldEngine``.
Structure is therefore never delegated — ``avoid_hairpins`` stays off, and a structural
objective is scored through the run's shared ``FoldEngine``.

**ESO is stochastic, and its randomness is not only ``random``.** DNAChisel draws from
both the stdlib generator and ``numpy.random``; seeding one leaves the other free, and
the same call then returns different sequences within one process, with the same seed.
Every ESO call here is therefore wrapped in ``_deterministic`` (both generators seeded
immediately before the call, both restored afterwards), and the seed is derived from the
run's seed plus the input — never from loop position, because each call consumes a
different amount of the stream and call order would change results.

**ESO also fails quietly.** It can return a sequence that violates a constraint it was
given and say so only through ``warnings.warn``; it trims input that is not a whole number
of codons without a word. Neither is allowed to reach a caller silently — see
``CodonOptimizer.variants``.
"""

import contextlib
import hashlib
import importlib.metadata
import io
import math
import random
import re
import warnings
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache

import python_codon_tables

from engine.domain import Host
from engine.errors import InputValidationError
from engine.gates.tools.ais_china import HOST_ID as AISC_HOST_ID
from engine.gates.tools.ais_china import REFERENCE_VERSION as AISC_REFERENCE_VERSION
from engine.gates.tools.ais_china import AisChinaCodons
from engine.gates.tools.folding import FoldEngine
from engine.sequences import (
    CODON_TABLE,
    STOP_CODONS,
    codons,
    gc_content,
    is_valid_rna,
    reverse_complement,
    to_dna,
    to_rna,
    translate,
    windows,
)

#: ESO's hotspot detector. ``"thorough"`` is Levenshtein-tolerant (a site that differs from
#: its twin by one edit is still a recombination substrate); ``"fast"`` is the exact-match
#: detector the original paper describes and misses those. A locked project decision, and
#: passed explicitly on every call rather than left to ESO's default so that a change of
#: ESO's default cannot change what this engine means. Reported by ``versions()``.
RECOMBINATION_MODE = "thorough"

#: ESO's slippage detector mode. ESO documents both modes as equally sensitive; recorded
#: for the same reason as ``RECOMBINATION_MODE``.
SLIPPAGE_MODE = "default"

#: Codon-optimisation method handed to ESO (DNAChisel's ``CodonOptimize``): the single best
#: codon per amino acid, i.e. the choice that maximises CAI. ESO then trades some of that
#: away wherever a hotspot or a constraint forces it.
_ESO_METHOD = "use_best_codon"

#: ESO's tables for the three hosts, by ``python_codon_tables`` name. **Never pass a raw
#: TaxID or an unlisted name to ESO or ``python_codon_tables``:** an unlisted name triggers
#: an HTTP fetch from Kazusa with a five-second timeout, in the middle of a run. These are
#: the tables the wheel ships. The *E. coli* table is strain 316407 (W3110), not MG1655.
_BUNDLED_TABLES: dict[Host, str] = {
    Host.ECOLI: "e_coli_316407",
    Host.YEAST: "s_cerevisiae_4932",
    Host.HUMAN: "h_sapiens_9606",
}

#: The one UserWarning ESO raises that says nothing about a constraint: ``CustomScore``
#: announcing that it is slow. Every *other* ESO UserWarning is a report that something it
#: was asked to do was not done, and is surfaced.
_ESO_PERFORMANCE_NOTICE = "CustomScore re-evaluates score_fn"

#: Only the first sentence of ESO's "could not satisfy constraint" warning names the
#: constraint; the rest is a generic explanation repeated verbatim every time.
_DROPPED_CONSTRAINT_SPLIT = " - dropping it"

#: Reported-only: ESO limits the *report* dataframes to this many sites, never the
#: constraints it builds. Large enough never to bind.
_REPORT_SITES = 100_000


@dataclass(frozen=True, slots=True)
class CodonVariant:
    """One synonymous rewrite of a coding sequence, with what is known to be wrong with it.

    Attributes:
        sequence: RNA, uppercase, translating to exactly the protein of the input.
        translation_score: CAI against the host's table (``translation_score``), or
            ``None`` when it cannot be computed — a CDS with no scorable codon.
        structure_deviation: Expected fraction of positions in the wrong pairing state
            against ``target_pairing`` (``FoldEngine.ensemble_defect`` divided by length),
            0.0 being a perfect match; ``None`` when no ``target_pairing`` was given.
        codons_changed: Codons that differ from the input.
        unresolved: Everything ESO or its post-check reported as not done: constraints
            ESO dropped because they could not be met, and hypermutable sites that
            remain. **Empty means ESO resolved everything it was asked to.** A non-empty
            tuple is not an error — a Met or Trp inside a homopolymer cannot be fixed by
            any synonymous change — but a caller that ignores it is ignoring a
            documented residual instability.
        seed: The seed ESO ran under, so the result can be reproduced; ``None`` for the
            unchanged input, which involved no ESO call.
    """

    sequence: str
    translation_score: float | None
    structure_deviation: float | None
    codons_changed: int
    unresolved: tuple[str, ...]
    seed: int | None

    @property
    def clean(self) -> bool:
        """True when nothing is recorded as unresolved."""
        return not self.unresolved


@contextmanager
def _deterministic(seed: int) -> Iterator[list[warnings.WarningMessage]]:
    """Run ESO reproducibly, silently on stderr, with its warnings captured.

    Seeds **both** the stdlib and the numpy global generators (DNAChisel's
    ``MutationChoice.random_variant`` draws from ``numpy.random``), and restores both on
    exit so that the caller's own streams are untouched. With only ``random`` seeded, six
    identical calls in one process returned six different sequences.

    Yields the list of warnings raised inside the block. They are *data*: ESO reports a
    dropped constraint only here.

    Process-global state is touched (both generators, the warnings filter and stderr), so
    this is safe in a worker *process* and not across threads in one process.
    """
    import numpy as np  # imported here: ESO pulls it in anyway, and the engine's import
    # time for everything that only scores codons should not pay for it.

    py_state = random.getstate()
    np_state = np.random.get_state()
    random.seed(seed)
    np.random.seed(seed % 2**32)
    try:
        with (
            warnings.catch_warnings(record=True) as caught,
            contextlib.redirect_stderr(io.StringIO()),  # tqdm/proglog progress bars
        ):
            warnings.simplefilter("always")
            yield caught
    finally:
        random.setstate(py_state)
        np.random.set_state(np_state)


def _enzyme_expressions(names: Sequence[str]) -> dict[str, re.Pattern[str]]:
    """Each enzyme's recognition site as a compiled pattern over DNA, by name.

    Read from DNAChisel's own enzyme table so that the check afterwards uses the very
    definition ESO was told to avoid. An unknown name is a ``ValueError`` here, before any
    optimisation runs, rather than ESO's identical error half way through.
    """
    import dnachisel

    patterns: dict[str, re.Pattern[str]] = {}
    for name in names:
        try:
            site = dnachisel.EnzymeSitePattern(name)
        except KeyError:
            raise ValueError(
                f"{name!r} is not a restriction enzyme DNAChisel knows (names are "
                "case-sensitive, e.g. 'BsaI', 'EcoRI')."
            ) from None
        patterns[name] = re.compile(site.expression)
    return patterns


def _enzyme_sites_present(dna: str, patterns: dict[str, re.Pattern[str]]) -> list[str]:
    """Names of the enzymes whose site occurs in ``dna`` on either strand."""
    other_strand = reverse_complement(dna, dna=True)
    return [
        name
        for name, pattern in patterns.items()
        if pattern.search(dna) or pattern.search(other_strand)
    ]


class CodonOptimizer:
    """Synonymous-codon search and translation scoring for one host.

    Holds the host's usage table, so every caller scores against the same organism.
    Constructing one per call site invites two stages disagreeing about what "good codon
    usage" means — **build once, in ``pipeline.build_tools()``** (the house rules reject a
    construction anywhere else).

    Args:
        host: The organism. Determines which usage table applies — *E. coli*, yeast and
            human have substantially different preferences. A host with no bundled table
            is refused with ``InputValidationError``; a new host is a deliberate addition
            to ``_BUNDLED_TABLES``, never a fall-through to another organism's numbers.
        usage_table: Codon to relative frequency, normally 0.0 to 1.0 within each amino
            acid's synonymous family, keyed by RNA or DNA codon. When omitted the
            bundled table for ``host`` is used. Must name all 61 sense codons, every
            frequency finite and **strictly positive**: a zero would make a codon's
            adaptiveness zero and silently collapse any CDS using it to a CAI of zero,
            and this class refuses to invent the floor that would avoid that. When
            supplied, ESO's own codon objective (which only knows its bundled tables) is
            replaced by this same table's CAI, so rewriting and scoring still agree.
        folder: The run's shared ``FoldEngine``. Needed only for ``variants`` with a
            ``target_pairing``; a structural objective folds through it and never through
            DNAChisel, so there is one temperature and one cache.
        seed: ``JobRequest.seed``. ESO's randomness is derived from this plus the input.

    Note:
        Frequencies are **within a synonymous family**, not across all 64 codons. A codon
        at 0.9 is used 90% of the time for *its amino acid*, not 90% of the time overall.
        Mixing those two conventions produces a scoring function that looks reasonable
        and ranks nonsense highly.

        Relative *adaptiveness* (frequency over the family's maximum, 1.0 for the best
        codon) is a different quantity with the same shape. CAI needs adaptiveness and is
        computed from frequency here; because it divides by the family maximum it is
        unchanged by which of the two a table is given in. Anything that *samples*
        codons in proportion to use (DNAChisel's ``match_codon_usage``) needs frequency —
        handing it adaptiveness is silently wrong, which is why the stored table is
        frequency.
    """

    def __init__(
        self,
        host: Host,
        usage_table: dict[str, float] | None = None,
        *,
        folder: FoldEngine | None = None,
        seed: int = 0,
        aisc: AisChinaCodons | None = None,
    ) -> None:
        self.host = host
        self.folder = folder
        self.seed = seed
        self._aisc: AisChinaCodons | None = None
        if usage_table is None and host is Host.C_ACNES:
            if aisc is None:
                raise InputValidationError(
                    f"Host {host.value!r} is scored against the AIS-China reference "
                    "package, so CodonOptimizer needs the run's shared AisChinaCodons. "
                    "pipeline.build_tools() constructs it for this host and passes it as "
                    "aisc=; constructing a second one here would load a second copy of "
                    "their reference package (CLAUDE.md §5)."
                )
            # C. acnes is not in python_codon_tables, and a generic bacterial table would
            # be the wrong answer rather than an approximate one: this host's model is the
            # point of the collaboration. The AIS-China team derived it from ATCC 6919's
            # own genome -- CAI from a 61-gene ribosomal reference set, tAI from its 45
            # tRNA loci -- so their table is what this host is scored against.
            #
            # usage_frequencies() is host_codon_counts.csv (frequency within family,
            # summing to 1.0), NOT cai_weights.csv (relative adaptiveness, max 1.0 per
            # family). Those are different numbers of the same shape; see that method's
            # docstring. Passing the wrong one would be invisible under use_best_codon and
            # wrong under match_codon_usage.
            self._aisc = aisc
            self._eso_organism: str | None = None
            self.usage_table = _validated_usage(self._aisc.usage_frequencies())
        elif usage_table is None:
            self._eso_organism = _bundled_table_name(host)
            self.usage_table = dict(_bundled_usage(self._eso_organism))
        else:
            self._eso_organism = None
            self.usage_table = _validated_usage(usage_table)
        if self._aisc is not None:
            # Their published CAI weights, not adaptiveness re-derived from their
            # frequencies. Both are "relative adaptiveness" shaped, but theirs comes from
            # the 61-gene ribosomal reference set (Sharp & Li's high-expression proxy)
            # while re-deriving from genome-wide frequencies answers a different question.
            # Using theirs makes CERNAL's translation_score agree with the `cai` their own
            # report carries for the same sequence; deriving our own left the two
            # disagreeing in the third decimal for no defensible reason, which is exactly
            # the "two numbers for one measurement" this repo is built to avoid.
            self._adaptiveness = _validated_adaptiveness(self._aisc.cai_relative_adaptiveness())
        else:
            self._adaptiveness = _relative_adaptiveness(self.usage_table)

    def versions(self) -> dict[str, str]:
        """What this tool's numbers depend on — written into the run's provenance.

        Without it "why does this run disagree with last month's?" is unanswerable: ESO is
        stochastic and version-sensitive, and the recombination detector it runs changes
        which sites exist at all.
        """
        return {
            "eso": importlib.metadata.version("evolutionary-stability-optimizer"),
            "dnachisel": importlib.metadata.version("dnachisel"),
            "python_codon_tables": importlib.metadata.version("python-codon-tables"),
            "codon_table": (
                self._eso_organism
                or (f"ais-china/{AISC_HOST_ID}@{AISC_REFERENCE_VERSION}" if self._aisc else None)
                or "caller-supplied"
            ),
            "eso_recombination_mode": RECOMBINATION_MODE,
            "eso_slippage_mode": SLIPPAGE_MODE,
            "eso_method": _ESO_METHOD,
            "codon_optimizer_seed": str(self.seed),
        }

    def variants(
        self,
        cds: str,
        target_pairing: str | None = None,
        *,
        count: int = 4,
        avoid_enzymes: Sequence[str] = (),
        acceptable: Callable[[str], bool] | None = None,
        on_rejected: Callable[[str, tuple[str, ...]], None] | None = None,
        gc_range: tuple[float, float] = (30.0, 70.0),
        gc_window: int = 50,
    ) -> list[CodonVariant]:
        """Synonymous rewrites of a coding sequence: same protein, different bases.

        Args:
            cds: The coding sequence to rewrite, RNA (DNA is accepted and converted). Must
                be a whole number of codons: **checked here**, because ESO would silently
                trim a partial codon and hand back a shorter sequence. Pass the region you
                want rewritten rather than a whole gene when ``target_pairing`` is used —
                the structural objective folds the whole of it on every trial mutation.
            target_pairing: Optional dot-bracket structure, **the same length as ``cds``**,
                that the rewrite should move *towards*. Supplied when the caller is trying
                to make a region pair (to extend a stem) or stop pairing (to free an RBS).
                It replaces the codon-usage objective with the expected fraction of
                positions in the wrong pairing state (``FoldEngine.ensemble_defect``), so
                a structure-driven rewrite may land on poor codons: read each result's
                ``translation_score``, do not assume it.
            count: How many ESO runs to make, each under its own seed. Folding and ESO are
                the expensive parts, so the list is capped here. Fewer come back when two
                runs agree (the codon-usage objective is nearly deterministic, so its
                variants typically differ by a handful of codons) or when one is rejected.
            avoid_enzymes: Restriction enzyme names (DNAChisel's spelling, e.g.
                ``"EcoRI"``, ``"BsaI"``) whose sites must not appear on either strand.
                A calling stage derives these from the assembly standard it screens with.
            acceptable: Predicate over a candidate (RNA), ``False`` rejecting it. **This
                is how the stage's ``MotifScreener`` is applied** without this module
                importing upward: bind ``screener.is_compliant`` in the caller. It also
                catches what ``avoid_enzymes`` cannot — homopolymer runs and the team's
                extra forbidden motifs.
            on_rejected: Called as ``on_rejected(sequence, reasons)`` for every candidate
                *not* returned. When omitted, a rejection raises a ``UserWarning``
                instead — a candidate never vanishes without a trace.
            gc_range: Allowed GC percent (0-100) inside every ``gc_window``. Declared
                here, not hidden: the default is the scoring profile's ``gc_content``
                range. Pass a host's own bounds where they are known.
            gc_window: Window, in nucleotides, over which GC is enforced (the whole
                sequence if it is shorter).

        Returns:
            ``CodonVariant`` records, **best first**: those with nothing unresolved before
            those with something, then by ``structure_deviation`` (lower) when a
            ``target_pairing`` was given, then by ``translation_score`` (higher), then by
            sequence so that ties cannot order differently between runs. The unchanged
            input is included when it passes every check a rewrite must pass and has no
            hypermutable site. Every one translates to the same protein as ``cds``.

        Raises:
            ValueError: for a malformed input (frame, alphabet, a ``target_pairing`` that
                is not balanced or not the right length, a missing ``folder``, an unknown
                enzyme, a bad ``count`` or GC range).

        Rejected (never returned, always reported): a candidate that encodes a different
        protein or length, that contains a listed enzyme site, that falls outside
        ``gc_range`` in any window, or that ``acceptable`` refuses. ESO is expected to
        honour all four and sometimes does not, so each is re-verified here rather than
        trusted.

        Returned but flagged (``unresolved``): hypermutable sites ESO could not remove.
        These are reported, not hidden, and not fatal.

        Reproducibility:
            Each ESO run is seeded from ``self.seed``, the host, ``cds``,
            ``target_pairing`` and the run's index — so the same call returns the same
            list, in the same order, in any process and under any ``PYTHONHASHSEED``.
            It does *not* depend on what was called before it.

        Layering:
            The old docstring told this method to screen with ``MotifScreener``. That
            class lives in ``engine.stages``, which this module may not import (imports
            point downward only), so the stage passes ``acceptable`` and ``avoid_enzymes``
            instead.
        """
        rna = to_rna(cds)
        if not is_valid_rna(rna):
            raise ValueError("cds must be a non-empty sequence of A, C, G and U (or T) only")
        if len(rna) % 3:
            raise ValueError(
                f"cds is {len(rna)} nt, not a whole number of codons. This rewrites codon by "
                "codon and ESO would silently trim the remainder; fix the frame upstream."
            )
        if count < 1:
            raise ValueError(f"count must be at least 1, got {count}")
        low, high = gc_range
        if not (0.0 <= low < high <= 100.0):
            raise ValueError(
                f"gc_range must satisfy 0 <= low < high <= 100 (percent), got {gc_range}"
            )
        if gc_window < 1:
            raise ValueError(f"gc_window must be positive, got {gc_window}")
        if target_pairing is not None:
            self._check_pairing(rna, target_pairing)
        enzymes = _enzyme_expressions(avoid_enzymes)

        def reject(sequence: str, reasons: tuple[str, ...]) -> None:
            if on_rejected is not None:
                on_rejected(sequence, reasons)
            else:
                warnings.warn(
                    f"codon variant rejected: {'; '.join(reasons)}", UserWarning, stacklevel=3
                )

        protein = translate(rna, stop_at_stop=False)
        results: dict[str, CodonVariant] = {}

        # The input itself, when it is already acceptable. Always assessed without ESO.
        failures = self._hard_failures(rna, rna, protein, enzymes, acceptable, gc_range, gc_window)
        if not failures and not self._remaining_sites(rna):
            results[rna] = self._record(rna, rna, target_pairing, (), None)

        for index in range(count):
            seed = self._derive_seed(rna, target_pairing, index)
            dna, notes = self._run_eso(
                to_dna(rna), target_pairing, enzymes, gc_range, gc_window, seed
            )
            candidate = to_rna(dna)
            if candidate in results:
                continue
            failures = self._hard_failures(
                candidate, rna, protein, enzymes, acceptable, gc_range, gc_window
            )
            if failures:
                reject(candidate, tuple(failures))
                continue
            unresolved = tuple(dict.fromkeys([*notes, *self._remaining_sites(candidate)]))
            results[candidate] = self._record(candidate, rna, target_pairing, unresolved, seed)

        ranked = sorted(results.values(), key=_ranking_key)
        return ranked[:count]

    def translation_score(self, cds: str) -> float | None:
        """How well a sequence's codons suit the host: its Codon Adaptation Index.

        Args:
            cds: The coding sequence, RNA (DNA accepted). In frame, whole codons.

        Returns:
            A score in (0.0, 1.0] where higher means better adapted, or ``None`` when the
            sequence has no scorable codon (it is empty of anything but Met, Trp and
            stops) — a measurement that cannot be made is not a score of zero. Stored as
            ``SwitchDesign.translation_score``. **It is not one of the nine scored
            metrics**: ``evaluate_design`` may not emit it (``gates/toehold.py``), so it
            is recorded beside a design and never weighted into its ranking.

        How:
            The geometric mean of each codon's relative adaptiveness — its frequency
            divided by the largest frequency among the codons for the same amino acid
            (Sharp & Li, 1987), exactly as ``exp(mean(log w))``. Geometric rather than
            arithmetic, so one catastrophic codon drags the score down rather than being
            averaged away.

            Stop codons are skipped wherever they occur. **Met and Trp are excluded**: each
            has a single codon, so its adaptiveness is 1.0 by construction and counting it
            would only dilute the score towards 1.0 in proportion to how Met/Trp-rich the
            protein is.

        Raises:
            ValueError: when ``cds`` is not a whole number of codons over A, C, G, U/T.
                A frame error scores a different protein, so it is refused, not scored.

        Note:
            CAI predicts expression *level*, not whether the switch works. A design can
            score 0.95 here and still be dark because its stem never opens.
        """
        rna = to_rna(cds)
        if rna and not is_valid_rna(rna):
            raise ValueError("cds must contain only A, C, G and U (or T)")
        if len(rna) % 3:
            raise ValueError(f"cds is {len(rna)} nt, not a whole number of codons")
        weights = [self._adaptiveness[c] for c in codons(rna) if c in self._adaptiveness]
        if not weights:
            return None
        return math.exp(sum(math.log(w) for w in weights) / len(weights))

    # ------------------------------------------------------------------ internals

    def _check_pairing(self, rna: str, target_pairing: str) -> None:
        if self.folder is None:
            raise ValueError(
                "target_pairing needs a FoldEngine; construct CodonOptimizer(host, folder=...) "
                "with the run's shared one (pipeline.build_tools does)."
            )
        if len(target_pairing) != len(rna):
            raise ValueError(f"target_pairing is {len(target_pairing)} long but cds is {len(rna)}")
        depth = 0
        for char in target_pairing:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth < 0:
                    break
            elif char != ".":
                raise ValueError(f"target_pairing may hold only '.', '(' and ')', got {char!r}")
        if depth != 0:
            raise ValueError("target_pairing is not balanced")

    def _derive_seed(self, rna: str, target_pairing: str | None, index: int) -> int:
        """A 64-bit seed from the run seed and the *input* — not from call order."""
        material = "\x1f".join(
            [str(self.seed), self.host.value, rna, target_pairing or "", str(index)]
        )
        return int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big")

    def _run_eso(
        self,
        dna: str,
        target_pairing: str | None,
        enzymes: dict[str, re.Pattern[str]],
        gc_range: tuple[float, float],
        gc_window: int,
        seed: int,
    ) -> tuple[str, list[str]]:
        """One ESO run: codon/GC pass, then detect-and-repair until stable.

        Mirrors ESO's own two-pass recipe (``eso.pipeline.backend``): the repair loop
        exists because a repair's codon choices can create a *new* hotspot that a single
        pass would never re-screen.

        Returns the DNA ESO produced and its warnings that report an unmet request.
        """
        from eso import optimization_engine
        from eso.pipeline import reoptimize_until_stable

        low, high = gc_range[0] / 100.0, gc_range[1] / 100.0
        window = min(gc_window, len(dna))
        score_fn, organism = self._objective(target_pairing)
        names = tuple(enzymes)

        with _deterministic(seed) as caught:
            first, _, _ = optimization_engine(
                dna,
                mini_gc=low,
                maxi_gc=high,
                window_size_gc=window,
                method=_ESO_METHOD,
                organism_name=organism,
                custom_score_fn=score_fn,
                avoid_enzymes=names,
                avoid_hairpins=False,  # structure is FoldEngine's alone
            )
            final, _, _, _, _ = reoptimize_until_stable(
                first,
                False,
                _REPORT_SITES,
                None,
                None,
                RECOMBINATION_MODE,
                SLIPPAGE_MODE,
                low,
                high,
                _ESO_METHOD,
                organism,
                score_fn,
                False,
                avoid_hairpins=False,
                avoid_enzymes=names,
            )
        notes = [
            str(w.message).split(_DROPPED_CONSTRAINT_SPLIT)[0]
            for w in caught
            if issubclass(w.category, UserWarning)
            and not str(w.message).startswith(_ESO_PERFORMANCE_NOTICE)
        ]
        return final, list(dict.fromkeys(notes))

    def _objective(self, target_pairing: str | None) -> tuple[Callable[[str], float] | None, str]:
        """ESO's ``custom_score_fn`` and ``organism_name`` for this call.

        ESO's ``custom_score_fn`` *replaces* its codon objective (it is not additive), so
        exactly one of the two is ever in force: the structural one when a
        ``target_pairing`` is given, otherwise ESO's bundled table when the host's own is
        in use, otherwise this instance's table expressed as a CAI.
        """
        if target_pairing is not None:
            folder = self.folder
            assert folder is not None  # _check_pairing

            def closeness(dna: str) -> float:
                rna = to_rna(dna)
                return -folder.ensemble_defect(rna, target_pairing) / len(rna)

            return closeness, "not_specified"
        if self._eso_organism is not None:
            return None, self._eso_organism

        def adaptation(dna: str) -> float:
            score = self.translation_score(dna)
            # ESO maximises; a CDS of only Met/Trp has nothing to adapt, and is the same
            # whatever is chosen, so any constant is correct here.
            return -1.0 if score is None else score

        return adaptation, "not_specified"

    def _hard_failures(
        self,
        candidate: str,
        original: str,
        protein: str,
        enzymes: dict[str, re.Pattern[str]],
        acceptable: Callable[[str], bool] | None,
        gc_range: tuple[float, float],
        gc_window: int,
    ) -> list[str]:
        """Every reason this candidate may not be offered, re-verified independently."""
        failures: list[str] = []
        if len(candidate) != len(original):
            failures.append(f"length changed from {len(original)} to {len(candidate)} nt")
        elif translate(candidate, stop_at_stop=False) != protein:
            failures.append("encodes a different protein")
        present = _enzyme_sites_present(to_dna(candidate), enzymes)
        if present:
            failures.append(f"contains a site for {', '.join(present)}")
        size = min(gc_window, len(candidate))
        outside = [
            start
            for start, window in windows(candidate, size)
            if not gc_range[0] <= gc_content(window) <= gc_range[1]
        ]
        if outside:
            failures.append(
                f"GC outside {gc_range[0]:g}-{gc_range[1]:g}% in {len(outside)} "
                f"window(s) of {size} nt, first at {outside[0]}"
            )
        if acceptable is not None and not acceptable(candidate):
            failures.append("refused by the caller's acceptability check")
        return failures

    def _remaining_sites(self, candidate: str) -> list[str]:
        """Hypermutable sites still present, by a fresh, independent detection pass.

        Detection is deterministic, so this needs no seeding. It does not trust the
        absence of a warning: a repair loop that hits its round cap ends with sites left
        and no warning at all.
        """
        from eso import suspect_site_extractor

        with warnings.catch_warnings(), contextlib.redirect_stderr(io.StringIO()):
            warnings.simplefilter("ignore")
            sites = suspect_site_extractor(
                to_dna(candidate),
                False,
                _REPORT_SITES,
                recombination_mode=RECOMBINATION_MODE,
                slippage_mode=SLIPPAGE_MODE,
            )
        found: list[str] = []
        recombination = len(sites["df_recombination_raw"])
        slippage = len(sites["df_slippage_raw"])
        if recombination:
            found.append(f"{recombination} recombination site(s) remain")
        if slippage:
            found.append(f"{slippage} replication-slippage site(s) remain")
        return found

    def _record(
        self,
        candidate: str,
        original: str,
        target_pairing: str | None,
        unresolved: tuple[str, ...],
        seed: int | None,
    ) -> CodonVariant:
        deviation = None
        if target_pairing is not None:
            assert self.folder is not None  # _check_pairing
            deviation = self.folder.ensemble_defect(candidate, target_pairing) / len(candidate)
        changed = sum(a != b for a, b in zip(codons(candidate), codons(original), strict=True))
        return CodonVariant(
            sequence=candidate,
            translation_score=self.translation_score(candidate),
            structure_deviation=deviation,
            codons_changed=changed,
            unresolved=unresolved,
            seed=seed,
        )


def _ranking_key(variant: CodonVariant) -> tuple:
    """Best first. ``None`` sorts after every number: an unmeasured score is not a good one."""
    deviation = variant.structure_deviation
    score = variant.translation_score
    return (
        bool(variant.unresolved),
        deviation is None,
        deviation if deviation is not None else 0.0,
        score is None,
        -score if score is not None else 0.0,
        variant.sequence,
    )


def _bundled_table_name(host: Host) -> str:
    name = _BUNDLED_TABLES.get(host)
    if name is None:
        raise InputValidationError(
            f"No codon-usage table is bundled for host {host.value!r}. Add it to "
            "codons._BUNDLED_TABLES deliberately, or pass usage_table=."
        )
    return name


@cache
def _bundled_usage(name: str) -> dict[str, float]:
    """The bundled table for ``name`` as RNA codon -> frequency within its family.

    ``python_codon_tables.get_codons_table`` hands back a cached, shared, mutable dict, so
    it is copied rather than kept. Its name argument falls through to an HTTP fetch for
    anything it does not recognise; refusing an unlisted name first keeps this offline.
    """
    if name not in python_codon_tables.available_codon_tables_names:
        raise InputValidationError(f"codon table {name!r} is not bundled with python-codon-tables")
    table = python_codon_tables.get_codons_table(name)
    return _validated_usage(
        {
            codon: freq
            for residue, family in table.items()
            if residue != "*"
            for codon, freq in family.items()
        }
    )


def _validated_usage(usage_table: dict[str, float]) -> dict[str, float]:
    """RNA-keyed copy of a codon-usage table, or ``ValueError`` saying what is wrong."""
    table = {to_rna(codon): float(freq) for codon, freq in usage_table.items()}
    sense = {codon for codon, residue in CODON_TABLE.items() if residue != "*"}
    missing = sorted(sense - table.keys())
    if missing:
        raise ValueError(f"usage_table is missing sense codon(s): {', '.join(missing)}")
    unknown = sorted(table.keys() - sense - STOP_CODONS)
    if unknown:
        raise ValueError(f"usage_table has non-codon key(s): {', '.join(unknown)}")
    bad = sorted(codon for codon in sense if not (math.isfinite(table[codon]) and table[codon] > 0))
    if bad:
        raise ValueError(
            f"usage_table needs a finite frequency above zero for every sense codon; "
            f"offending: {', '.join(bad)}"
        )
    return {codon: table[codon] for codon in sorted(sense)}


def _validated_adaptiveness(weights: dict[str, float]) -> dict[str, float]:
    """RNA-keyed copy of a CAI weight table, or ``ValueError`` saying what is wrong.

    Same contract ``_relative_adaptiveness`` produces, checked because this table comes
    from outside: every sense codon present, every weight finite, strictly positive and at
    most 1.0. Zero would collapse any CDS using that codon to a CAI of 0 through the
    geometric mean, and this module will not invent a floor to hide that. A value above
    1.0 means someone passed frequencies or raw counts, which have the same shape and are
    a different quantity.
    """
    table = {to_rna(codon): float(w) for codon, w in weights.items()}
    sense = {codon for codon, residue in CODON_TABLE.items() if residue != "*"}
    missing = sorted(sense - table.keys())
    if missing:
        raise ValueError(f"CAI weight table is missing sense codon(s): {', '.join(missing)}")
    bad = sorted(c for c in sense if not (math.isfinite(table[c]) and 0.0 < table[c] <= 1.0))
    if bad:
        raise ValueError(
            "CAI weights must be finite and in (0.0, 1.0] -- relative adaptiveness, not "
            f"frequencies or counts; offending: {', '.join(bad)}"
        )
    # Drop single-codon families, exactly as _relative_adaptiveness does: Met and Trp have
    # one codon each, so w == 1.0 by construction and including them dilutes the geometric
    # mean towards 1.0 in proportion to how Met/Trp-rich the protein is. Returning all 61
    # here instead of 59 is what made this score disagree with the collaborators' own
    # reported CAI for the same sequence in the third decimal.
    scoreable = {c for c in sense if sum(1 for d in sense if CODON_TABLE[d] == CODON_TABLE[c]) > 1}
    return {codon: table[codon] for codon in sorted(scoreable)}


def _relative_adaptiveness(usage_table: dict[str, float]) -> dict[str, float]:
    """Frequency over its family's maximum, for every codon that has a synonym.

    Met and Trp (one codon each) are left out on purpose — see
    ``CodonOptimizer.translation_score``. Stops never reach here.
    """
    families: dict[str, list[str]] = {}
    for codon in usage_table:
        residue = CODON_TABLE[codon]
        if residue != "*":
            families.setdefault(residue, []).append(codon)
    adaptiveness: dict[str, float] = {}
    for members in families.values():
        if len(members) < 2:
            continue
        best = max(usage_table[codon] for codon in members)
        for codon in members:
            adaptiveness[codon] = usage_table[codon] / best
    return adaptiveness
