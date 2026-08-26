"""Gate family lookup.

Families register themselves here by name. The pipeline resolves the names a researcher
requested (``JobRequest.gate_families``) into classes, so adding a chemistry means
adding a module and one ``register()`` call — nothing else changes.
"""

from engine.contract import GateFamilyInfo
from engine.errors import UnsupportedGateFamilyError
from engine.gates.base import GateFamily
from engine.gates.planned import AntisenseGate, CrisprGate
from engine.gates.toehold import ToeholdGate

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


def available_families() -> list[str]:
    """Names that can actually be selected for a run."""
    return sorted(name for name, family in _REGISTRY.items() if family.available)


def describe_families() -> list[GateFamilyInfo]:
    """Every registered family, including the ones that are only planned."""
    return [
        GateFamilyInfo(
            name=family.name,
            label=family.label or family.name,
            description=family.description,
            available=family.available,
        )
        for _name, family in sorted(_REGISTRY.items())
    ]


register(ToeholdGate)
register(CrisprGate)
register(AntisenseGate)
