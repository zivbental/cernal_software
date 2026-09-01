"""Scientific primitives shared across the gate families.

A tool is an ordinary class (or module) that takes sequences and returns facts. It has
no opinion about why it is being called — a gate family **uses** one rather than
inheriting from it (docs/engine.md §2.4).

**What lives here, and what does not.** These four are the primitives more than one
chemistry needs in order to *build and measure a switch*: folding (S2, S4), hybridisation
energy (S3), codon rewriting (S8) and translation initiation (S9). A toehold, an
antisense element and a blocked sgRNA all fold, and all must report the same quantity on
the same scale — two families computing "binding energy" slightly differently produce
numbers that ``engine.scoring`` will normalise onto one axis as though they were
comparable.

Primitives that no gate family uses live with the pipeline step that does:

* ``engine.stages.folding`` — ``FoldProfiler`` (S1). A gate is handed a trigger that has
  already been judged accessible; only stage 2 asks that question.
* ``engine.stages.off_target`` — ``OffTargetScanner`` (S5). Stages 2, 3 and 4.
* ``engine.stages.motifs`` — ``MotifScreener`` (S7). Stages 2, 3 and 5.
* ``engine.sequences`` — pure sequence functions (S6), used by everything, and therefore
  at the engine root rather than under any one layer.

Everything here imports nothing but ``engine.domain``, ``engine.sequences`` and its
scientific library, which is what makes each one testable with no pipeline around it.
"""
