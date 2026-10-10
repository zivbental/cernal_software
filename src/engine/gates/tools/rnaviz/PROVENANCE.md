# cernal-rnaviz drawing primitives

- Source: https://github.com/talberez/cernal-rnaviz
- Pinned commit: `aa112e17a76941233987bb4287c2c66511c40d13`
- Copyright: 2026 iGEM TAU 2026 Team, Tel Aviv University
- License: Apache-2.0; upstream `LICENSE` and `NOTICE` are preserved here verbatim.
- Imported source: `src/cernal_rnaviz/layout.py` (`build_bases_and_links`) and
  `src/cernal_rnaviz/models.py` (`Base`, `Link` and their serialization).
- Modifications: added attribution headers; omitted dimer classification, unused
  constants, fold/cofold result types and unused imports; adjusted the model module
  description. The node/pair construction and retained data types are unchanged.

No upstream folding, API, private documentation, configuration or history is included.
The package is a drawing primitive, not a second scientific engine. The existing
`engine.gates.tools.folding.FoldEngine` adapter generates geometry for a stored,
validated dot-bracket string. It explicitly selects ViennaRNA NAVIEW using
`naview_xy_coordinates`, matching upstream `get_xy_coordinates` with its default
NAVIEW setting, without changing process-global plot settings. The SWIG tuple's
trailing sentinel is discarded. A one-nucleotide structure is placed at `(0, 0)`
because ViennaRNA 2.7.2 NAVIEW returns nonfinite coordinates for that input.

The 2,000 nucleotide viewer limit bounds native layout work and response size; it
is not a scientific design constraint. Stored sequences, structures, provenance,
metrics and run results are never modified or recomputed.
