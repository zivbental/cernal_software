"""The thirteen scientific stages, in order.

**Stubs.** Signatures and ordering are final; the bodies land in Step 5
(docs/software-design.md §13). Each docstring records what the stage owes its successor
so that implementing it is a scientific problem, not an architectural one.

Reference: design map 11, "Scientific Pipeline". Stage numbering matches that map.

Design note carried over from the map: this is a sequence of small functions rather than
one monolith, because gate families branch and rejected candidates must survive with a
reason attached rather than vanishing.
"""

from collections.abc import Iterable
from typing import Any

from engine.contract import ArtifactRef, CandidateResult, JobRequest
from engine.gates.base import Constraints, GateDesign, Trigger, TriggerSet
from engine.scoring.profiles import ScoringProfile


def validate_inputs(request: JobRequest) -> None:
    """1. Scientific input validation.

    Beyond the Platform's shallow format check: required metadata present, expression
    matrix semantics coherent, organism supported, constraints internally consistent.
    Raises ``InputValidationError``.
    """
    raise NotImplementedError("Step 5")


def load_and_preprocess(request: JobRequest) -> Any:
    """2. Read the immutable input and normalize it per a versioned preprocessing profile.

    Differential expression is supplied *by the researcher* — we do not compute DGE
    (design map 11, stage 3 note).
    """
    raise NotImplementedError("Step 5")


def discover_features(data: Any, constraints: Constraints) -> list[Trigger]:
    """3. Identify features that discriminate the base from the target state.

    Optional future extension, explicitly out of scope for the first implementation:
    cross-referencing external databases.
    """
    raise NotImplementedError("Step 5")


def generate_trigger_sets(
    triggers: list[Trigger], constraints: Constraints
) -> Iterable[TriggerSet]:
    """4. Combine features into 1-, 2- or higher-order trigger sets within constraints."""
    raise NotImplementedError("Step 5")


def evaluate_triggers(trigger_set: TriggerSet) -> dict[str, float | None]:
    """5. Trigger-level metrics: separation quality, expression bounds, accessibility."""
    raise NotImplementedError("Step 5")


def generate_gates(
    trigger_set: TriggerSet, families: list[str], constraints: Constraints
) -> Iterable[GateDesign]:
    """6. For each valid trigger set, ask every requested family for realisations."""
    raise NotImplementedError("Step 5")


def evaluate_gates(design: GateDesign) -> dict[str, float | None]:
    """7. Family-specific evaluation: structure, compatibility, leakage and activation."""
    raise NotImplementedError("Step 5")


def construct_circuits(designs: Iterable[GateDesign]) -> Iterable[Any]:
    """8. Assemble triggers and gates into complete candidate circuits and logic graphs."""
    raise NotImplementedError("Step 5")


def normalize_metrics(raw: dict[str, float | None], profile: ScoringProfile) -> Any:
    """9. Convert heterogeneous raw metrics onto comparable axes.

    Already implemented generically in ``engine.scoring.normalize``. Step 5 supplies the
    free-energy-based rules and any complexity penalty the scientific team settles on.
    """
    raise NotImplementedError("Step 5")


def score_candidates(candidates: Iterable[Any], profile: ScoringProfile) -> Iterable[Any]:
    """10. Apply the declared profile and weights, preserving raw and normalized values."""
    raise NotImplementedError("Step 5")


def rank_and_filter(candidates: Iterable[Any], profile: ScoringProfile) -> list[CandidateResult]:
    """11. Rank survivors and keep rejections with explicit reasons (rule 8)."""
    raise NotImplementedError("Step 5")


def generate_artifacts(candidates: list[CandidateResult], output_dir: str) -> list[ArtifactRef]:
    """12. Sequences, design tables, logic graph data, diagnostic plots, warnings."""
    raise NotImplementedError("Step 5")


def publish_result(
    request: JobRequest, candidates: list[CandidateResult], artifacts: list[ArtifactRef]
) -> Any:
    """13. Assemble the checksummed result manifest with every version and parameter."""
    raise NotImplementedError("Step 5")
