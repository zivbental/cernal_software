"""The pipeline stages.

One module per stage of the CERNAL Computational Pipeline Map, named so that someone
reading the map can find the code. Each stage is a class holding read-only
configuration and the tools it uses, with one public method taking the previous stage's
records and returning the next (docs/engine.md §3.1).

Stages hold configuration, never accumulated state — that distinction is what keeps
each one testable in isolation (docs/engine.md §2.3).

Alongside the stage modules sit the three scientific primitives that **no gate family
uses**, each shared by two or three stages:

* ``folding.py`` — ``FoldProfiler`` (S1). Accessibility of a window in its transcript.
  Stage 2 only; a gate is handed a trigger already judged accessible.
* ``off_target.py`` — ``OffTargetScanner`` (S5). Stages 2, 3 and 4.
* ``motifs.py`` — ``MotifScreener`` (S7). Stages 2, 3 and 5.

They are modules here rather than copies inside each stage for the reason docs/engine.md
§3.4 sets out at length: three transcriptome indexes means three mismatch conventions and
three penalty scales, and ``engine.scoring`` would normalise them onto one axis as though
they were comparable. One implementation, several callers, each asking its own question.

The primitives the **gate families** share — folding, hybridisation energy, codons,
translation initiation — live in ``engine.gates.tools`` instead.
"""
