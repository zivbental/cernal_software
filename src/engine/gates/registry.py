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
    """Register a gate family. Usable as a class decorator."""
    if not family.name:
        raise ValueError(f"{family.__name__} must set a non-empty `name`.")
    if not family.version:
        raise ValueError(f"{family.__name__} must set a non-empty `version`.")
    _REGISTRY[family.name] = family
    return family


def get_family(name: str) -> type[GateFamily]:
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(available_families()) or "none"
        raise UnsupportedGateFamilyError(
            f"Unknown gate family '{name}'. Available families: {known}."
        ) from None


def available_families(host: Host | None = None) -> list[str]:
    """Names that can actually be selected, optionally for one host.

    CRISPR is eukaryotic only, so availability depends on both.
    """
    return sorted(
        name
        for name, family in _REGISTRY.items()
        if family.available and (host is None or host in family.supported_hosts)
    )


def describe_families(host: Host | None = None) -> list[GateFamilyInfo]:
    """Every registered family, including the ones only planned.

    ``available`` accounts for the host when one is given, so the UI can grey out CRISPR
    for E. coli rather than accepting a submission that cannot be built.
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
