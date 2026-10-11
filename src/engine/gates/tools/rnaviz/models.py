# Adapted from cernal-rnaviz, commit aa112e17a76941233987bb4287c2c66511c40d13.
# Copyright 2026 iGEM TAU 2026 Team, Tel Aviv University. Apache-2.0.
# See LICENSE, NOTICE and PROVENANCE.md in this directory for source and modifications.

"""Drawable nucleotide and base-pair types adapted from cernal-rnaviz.

Every type carries a ``to_dict`` that produces exactly the JSON the web client
consumes. Keeping the serialisation next to the data — rather than in the HTTP
layer — is what lets a CERNAL pipeline write the same payload to a file without
starting a server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

JsonDict = dict[str, Any]


@dataclass(slots=True)
class Base:
    """One nucleotide, with the 2D layout coordinates ViennaRNA computed for it."""

    index: int
    char: str
    x: float
    y: float

    def to_dict(self) -> JsonDict:
        return {"index": self.index, "char": self.char, "x": self.x, "y": self.y}


@dataclass(slots=True)
class Link:
    """A base pair between two nucleotides, by index into the base list.

    ``source`` is always the 5'-most partner. ``probability`` is set only when
    the partition function was computed, and ``type`` only for a dimer, so that
    the serialised payload stays identical to what the client already handles.
    """

    source: int
    target: int
    probability: float | None = None
    type: str | None = None

    def to_dict(self) -> JsonDict:
        payload: JsonDict = {"source": self.source, "target": self.target}
        if self.type is not None:
            payload["type"] = self.type
        if self.probability is not None:
            payload["probability"] = self.probability
        return payload
