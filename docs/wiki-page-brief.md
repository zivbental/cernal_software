# The iGEM model page — standing brief

Everything the wiki page has to satisfy, in one place, so none of it has to be re-explained.
Written down because it was given once and the page will be built over many sittings.

---

## 1. Where the page lives

| | |
|---|---|
| wiki repo | `https://gitlab.igem.org/2026/tau-israel.git` |
| our page | `wiki/pages/model.html` — a **subpage under the Model page** |
| rule | **touch no other page.** Adopt the existing visual language and style from the start rather than adding ours later |
| last year's, as the style reference | `https://2025.igem.wiki/tau-israel/model` |

Two drafts already exist and either can be continued:
- model page: `https://claude.ai/artifact/FRiqiH6mWd3DNrKZFqFcQn`
- judge-book research: `https://claude.ai/artifact/1ZdFUA3CaEBZztvQiUZEVs`
- threshold evidence, the supplementary candidate: `https://claude.ai/artifact/D46u14hLnq1BL7tsJj7hk3`

A tracked Markdown mirror lives at `docs/igem-model-page.md`.

---

## 2. The required section format

Given verbatim:

- **ABSTRACT & INTRODUCTION** — background and the theory the work rests on
- **a graphical flow / architecture diagram, with notations**
- **MATERIALS & METHODS** — the computational components that make up the algorithm, defined
  well enough for reproducibility, **with links to the code on GitHub**
- **DATA** — only if there is something particular to say about it
- **RESULTS** — experiments, engineering cycles, computational validation where done
- **DISCUSSION / CONCLUSIONS** — weighted toward the four iGEM questions: validation against
  real published data, what the model taught us, sensitivity analysis. **Emphasise mistakes and
  things that did not come out as expected, and try to explain them**
- **REFERENCES**
- **SUPPLEMENTARY DATA** — a separate page, so the wiki page stays readable

Plus, through the whole of Methods: **per-step graphical "simulations"** — feed a module an
example input and show its output. Enter a sequence, get a gate diagram; enter a gene, find a
trigger in it.

---

## 3. Style and length

- **Graphs are the intellectual core of the chapter**, not decoration. Informative figures of the
  algorithms, of the results, and of the analyses that decided the algorithm — for example, the
  comparison against measured libraries that chose the trigger-ranking function.
- Everything technical belongs here at the level of a paper's Methods.
- Worked example of a computational paper to match:
  `C:\Users\Dell\OneDrive - mail.tau.ac.il\IGEM\WIKI\more articles\dsx049.pdf`
- **Figure style for the gate structure:**
  `C:\Users\Dell\OneDrive - mail.tau.ac.il\IGEM\Toehold\prokaryotic_and_gate_two_toeholds_1.svg`
  Needs adapting and correcting to our actual architecture, **and versions for states 01 and 10**.
- Length: it will not be short, but be purposeful. No circling. Deep dives go to the
  supplementary page to keep the wiki page accessible and readable.

---

## 4. What the judges score (`Judges criterias.txt`)

The Engineering Methodology outline reads as a section list, and the page should map onto it:

1. identify and demonstrate understanding of the problem
2. gather data, cite sources, **recognise unknowns and constraints**
3. select applicable guiding principles and theories
4. **list assumptions, approximations and simplifications**
5. **establish quantifiable measures of success**
6. show how the problem was solved
7. **validate the results**
8. communicate the solution

Specific notes that change what we write:

- **The approach must be "middle-out"**, between forward and backward engineering, **defining
  knowns and unknowns**. That is exactly what the conditional-lever work is: the right balance
  between `a_site_energy`, `b_site_energy` and the lock is unknown, so the space is enumerated;
  where a lever has been measured, it narrows. Name it as middle-out explicitly.
- "The best engineered projects are often not the largest" — a clearly defined problem with
  stated criteria for success beats breadth.
- Reproducibility is an explicit judging question, as is whether others can build on the work.
- Either *predict behaviour to guide design* or *build models that characterise and explain how
  the system works*. **We are the second**, and should say so rather than overclaiming the first.
- Quantitative measurements: appropriate units, clear reporting, comparison against controls.
- **Silver medal** needs at least one Design → Build → Test → Learn iteration **and** a statement
  of what we would change in the next one.
- RFC 10 / RFC 1000 assembly compatibility is auto-screened by the Registry.
- Part documentation is scored **on the Registry only**, not on the wiki.

---

## 5. Assumptions — as corrected, and each with what it hides

Numbered as agreed. Several are an assumption **and** a limitation, and the page says so in both
places rather than picking one.

1. **Thermodynamic equilibrium.** Every number is an equilibrium ensemble property. No kinetics,
   no folding path, no co-transcriptional order. *Also a limitation* — it is why Kim's four
   constructs cannot be told apart by anything we compute.
2. **Which span is folded, and which span is measured.** Two separate decisions.
   - The toehold genuinely sits in the **5′ UTR**, most of it before the AUG — that is the
     architecture, not an approximation.
   - The assumption is about **length**: a folding model over too long a molecule predicts
     poorly, so the switch (161–167 nt) plus the triggers is folded rather than a whole mRNA.
   - And the measured span was **widened to include the linker** so as not to be too narrow.
   *Also a limitation*: the trigger windows come from bundled **CDS-only** sequences, with no
   UTRs and no operon context, so a trigger's accessibility is folded on an incomplete molecule.
3. **The parameter model**, verified in the code rather than assumed: **ViennaRNA 2.7.2**, model
   details carried explicitly on an `RNA.md()` — `temperature 37.0`, `dangles 2`,
   `special_hp 1`, `noLP 0`, `noGU 0`. The energy parameters are ViennaRNA 2.x's **defaults,
   which are Turner 2004**; `rna_turner1999.par` ships with the library and is never loaded.
   **Reproducibility gap to fix:** `FoldEngine.versions()` records ViennaRNA and the temperature
   but **not** the parameter set or the model details.
4. **Each window is measured with the statistic that matches what reads it** — and we use both,
   so this is not "mean instead of joint":
   - **joint** probability that a whole window is open at once (`p_open`), converted to an
     energy by `−RT·ln p` (`open_penalty`). This is what `open_11`, `dG_open_*` and the opening
     separation ride on, and it is the right one for a ribosome footprint: the 30S entry channel
     holds single-stranded RNA and the whole threaded window must be open simultaneously.
   - **mean** per-base unpaired probability (`_mean_unpaired`), for `A_M`, `A_S`, `meanW`, `aug` —
     "is this region generally reachable", where a joint probability over 18 nt would be ~1e-22
     for every design and discriminate nothing.
   - **IED**, the mean *paired* probability over the RBS-loop-to-linker span, which is VISTA's
     Ideal Ensemble Defect for a region specified as completely unpaired.
   The assumption is that these three are matched to the right questions.
5. **That the one-input idea extends to the way we measure a two-input gate** — to the A_M
   ratio, the gains and the separations. The *calibration* against single-input libraries is a
   **limitation**, not an assumption, and belongs in that section.

---

## 6. The distinction the page must carry

**The pipeline and the experiment are two different things and must not be blurred.**

| | the PIPELINE | the mCherry EXPERIMENT |
|---|---|---|
| what it is | the generic platform: a transcriptomic signature in, an RNA circuit out | one input sequence that happens to contain two trigger windows |
| demonstrated on | **PFAS in *E. coli*** — `ggt`, `fadB`, `astC`, `aldA`, two windows on two different mRNAs | **mCherry**, both windows inside one 711-nt transcript |
| why it exists | the product | the characterisation bench: it is where the four-tube method, the levers and the thresholds were worked out, and it is comparable with every earlier sweep |
| what it can say | that the platform runs end to end on a real target | how the architecture behaves, with controls that a cross-gene pair cannot have |

*E. coli* and PFAS are the **use case, not the essence.** Every number on the page is labelled
with the dataset it was measured on, and **no metric in this work has held its sign across
datasets** — see `docs/findings-register.md`.

---

## 7. Where the numbers come from

`docs/findings-register.md` — one row per measured finding: the number, the file holding its
reasoning, the dataset, and the command that reproduces it. 99 rows. Nothing goes on the page
that is not in there with an `n` beside it.
