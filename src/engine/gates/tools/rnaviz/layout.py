# Adapted from cernal-rnaviz, commit aa112e17a76941233987bb4287c2c66511c40d13.
# Copyright 2026 iGEM TAU 2026 Team, Tel Aviv University. Apache-2.0.
# See LICENSE, NOTICE and PROVENANCE.md in this directory for source and modifications.

"""Turning ViennaRNA output into something drawable.

ViennaRNA gives a dot-bracket string, a pair table and a list of 2D coordinates.
The client needs nodes and edges. This module is the only place that conversion
happens, for both the single fold and each half of a dimer.
"""

from __future__ import annotations

from typing import Any

from .models import Base, Link


def build_bases_and_links(
    sequence: str,
    coordinates: Any,
    pair_table: Any,
    start_offset: int = 0,
) -> tuple[list[Base], list[Link]]:
    """Build the node and edge lists for one folded strand.

    Args:
        sequence: Nucleotides only — no ``&`` separator.
        coordinates: The object returned by ``RNA.get_xy_coordinates``.
        pair_table: The 1-indexed pair table returned by ``RNA.ptable``.
        start_offset: Added to every emitted index. Used when a strand is part of
            a dimer and its indices have to stay global.

    Returns:
        ``(bases, links)``. A pair appears once, on its 5'-most partner, so the
        client never draws the same hydrogen bond twice.
    """
    bases: list[Base] = []
    links: list[Link] = []

    for i, char in enumerate(sequence):
        point = coordinates.get(i)
        bases.append(Base(index=i + start_offset, char=char, x=point.X, y=point.Y))

        partner = pair_table[i + 1]
        if partner > i + 1:
            links.append(Link(source=i + start_offset, target=partner - 1 + start_offset))

    return bases, links
