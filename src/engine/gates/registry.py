"""Gate family lookup.

Families register themselves here by name. Adding a chemistry is a new module plus one
``register()`` call — nothing else changes.
"""

from engine.contract import GateFamilyInfo
from engine.domain import Host
from engine.errors import UnsupportedGateFamilyError
from engine.gates.antisense import AntisenseNotGate
from engine.gates.base import GateFamily
from engine.gates.crispr import CrisprGate
from engine.gates.toehold import ToeholdAndGate, ToeholdGate

_REGISTRY: dict[str, type[GateFamily]] = {}


def register(family: type[GateFamily]) -> type[GateFamily]:
    """Make a gate family visible to the pipeline and to the API.

    Args:
        family: The class, not an instance — instances are built per run with their
            tools, and the registry holds the type.

    Returns:
        The same class, so this works as a decorator.

    Raises:
        ValueError: if ``name`` or ``version`` is unset. Both end up on stored results:
            ``name`` identifies the chemistry, ``version`` is what lets an old design be
            traced back to the rules that produced it. A family without them would
            produce untraceable output.

    Adding a family is this call plus one module. Nothing else in the engine, the API or
    the frontend changes.
    """
    if not family.name:
        raise ValueError(f"{family.__name__} must set a non-empty `name`.")
    if not family.version:
        raise ValueError(f"{family.__name__} must set a non-empty `version`.")
    _REGISTRY[family.name] = family
    return family


def get_family(name: str) -> type[GateFamily]:
    """Look up a family class by name.

    Raises:
        UnsupportedGateFamilyError: naming the families that *are* available, so the
            message tells the caller what to do instead of only what went wrong.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(available_families()) or "none"
        raise UnsupportedGateFamilyError(
            f"Unknown gate family '{name}'. Available families: {known}."
        ) from None


def available_families(host: Host | None = None) -> list[str]:
    """Names a submission may legitimately request.

    Args:
        host: When given, restricts to families supporting that organism.

    Returns:
        Sorted names. Excludes families that are registered but not yet implemented, so
        the Platform validates submissions against this and refuses an unbuildable one at
        submit time rather than failing the run ten minutes later.

    Availability is a function of **gate and host**, not of gate alone: CRISPR is
    eukaryotic, so ``available_families(Host.ECOLI)`` omits it while
    ``available_families(Host.HUMAN)`` would include it once implemented.
    """
    return sorted(
        name
        for name, family in _REGISTRY.items()
        if family.available and (host is None or host in family.supported_hosts)
    )


def describe_families(host: Host | None = None) -> list[GateFamilyInfo]:
    """Everything the UI needs to render the mechanism choices.

    Args:
        host: When given, ``available`` accounts for it.

    Returns:
        One ``GateFamilyInfo`` per registered family — **including planned ones**, with
        ``available=False``.

    Why planned families are included:
        So the wizard can show CRISPR greyed out with its real label and description,
        rather than the frontend keeping its own hardcoded list of "coming soon" cards
        that nobody remembers to update. When a family is implemented, flipping
        ``available`` on the class changes the UI with no frontend release.

    Surfaced through ``EngineCapabilities`` at ``GET /api/version``.
    """
    return [
        GateFamilyInfo(
            name=family.name,
            label=family.label or family.name,
            description=family.description,
            available=family.available and (host is None or host in family.supported_hosts),
        )
        for _name, family in sorted(_REGISTRY.items())
    ]


register(ToeholdGate)
register(ToeholdAndGate)
register(AntisenseNotGate)
register(CrisprGate)
