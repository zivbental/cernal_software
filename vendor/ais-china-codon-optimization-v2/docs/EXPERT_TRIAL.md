# Codon V2 — Short Expert Trial

This is a computational tool with online and local modes for *Cutibacterium acnes* ATCC 6919 and KPA171202. We would appreciate feedback on the workflow, usefulness of the output choices, clarity of the results and modeling assumptions. No wet-lab work is requested.

## Start

Use the online application linked in the [README](../README.md), or run a local copy. Online calculations are sent to the deployment server; download results before leaving the page.

For local use, install Python 3.12. From the project directory:

```text
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:8765`. On Linux/macOS, use `.venv/bin/python` instead of `.venv\Scripts\python.exe`. Numerical checks were run on Windows; those additional platforms have not been tested for this release.

## A five-minute trial

1. Click **Load example**. This loads a real KPA171202 ribosomal CDS, selects ATCC 6919 as the target and enables all five independent strategies. The missing upstream sequence is explicitly labeled as CDS-only RNA analysis.
2. Click **Optimize sequence**. The page scrolls to the output. Each selected strategy runs independently with its own status and budget.
3. The complete DNA appears first, with its target host and preference label. Click **Copy sequence** or **Download FASTA**. No table selection is needed. Optional metrics, protein/constraint checks and further details are in the expandable analysis.
4. Each selected preference returns **one sequence**. Click a card under **Switch preference** to display its result. The first selected preference is shown initially; if it produces no valid sequence, an explicit message explains the fallback. This display order does not predict which strategy will express best. An unchanged output is clearly labeled.
5. Optionally expand **Metrics & comparison**. Inspecting a result or the original input does not replace the main output. Click **Use this sequence** to select another preference's result. Check rows for batch comparison or FASTA/CSV/JSON export. Identical DNA is exported once with all strategy memberships retained. Each preference has a single output, without numbered alternatives.

You can also try your own single CDS. If available, provide the actual transcribed upstream sequence adjacent to the start codon; it remains fixed. The genetic code is NCBI table 11. Harmonization requires a source-host reference; two built-in references and custom whole-CDS codon counts are supported.

## What the strategies mean

| UI label | Objective |
|---|---|
| 5′ RNA accessibility | Lower joint opening free energy; changes limited to codons 2–30 by default |
| Host frequency sampling | Generate synonymous sequences using host conditional codon frequencies |
| CAI priority | Increase strain-specific ribosomal-reference CAI |
| tAI priority | Increase the selected tRNA decoding-model score |
| Codon harmonization | Match the source host's synonymous-family codon ranks |

These searches run independently without a weighted ensemble or sequential rewriting. All share motif, GC and fixed-position rules. Final sequences are checked for protein identity. The original input is the default baseline.

## Feedback that would help

- Was any input or result difficult to understand?
- Could you immediately find, copy and download the output? Was switching preferences clear?
- Are the optional metric comparisons useful for your work?
- Which modeling assumption or missing analysis would you change first?
- If something failed, what did you expect to happen?

For an unexpected result, include the downloaded JSON report if you are comfortable sharing its sequence content. It contains the input, normalized settings, data hashes, seeds and stopping reasons needed to investigate.

The model uses public genomic references and inferred tRNA decoding, not measured tRNA abundance. CAI, tAI and RNA changes are not converted into expression fold changes. Trial feedback is not treated as experimental validation or endorsement of individual candidates.
