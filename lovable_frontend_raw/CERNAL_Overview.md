# CERNAL — Project Overview

**Team:** TAU iGEM 2025, Tel Aviv University
**Tagline:** Compiler-like Engine for RNA Logic

## What it is
CERNAL is a computational pipeline (web app) that turns transcriptomic signals into manufacturable synthetic gene circuits. Researchers define activation conditions as constraints; CERNAL outputs an optimized genetic blueprint (plasmid) with high signal-to-noise ratio.

Core idea: RNA-based switches (toehold switches, CRISPR guide RNAs) follow universal thermodynamics regardless of host organism, so circuits built this way are organism-agnostic — works in E. coli, yeast, or mammalian cells.

## Webapp flow (3 steps)
1. **Inputs** — Define organism (E. coli / Yeast / Human) and input mode:
   - Differential Expression: upload DE analysis (csv/tsv/xlsx) with fold-change column
   - Custom mRNA Trigger: paste/upload the exact trigger mRNA sequence directly
2. **Payload** — Choose downstream output:
   - Reporters (visual validation): GFP, mCherry, Luciferase
   - Selective markers (functional): Antibiotic resistance (AmpR/KanR, positive selection) or Apoptosis inducer (kill-switch, negative selection)
   - Custom output: user-pasted mRNA coding sequence
3. **Fulfillment** — CERNAL ranks candidate sequences (structural folding, leakage modeling, off-target screening) and shows:
   - Plasmid map view and logic-circuit view (AND/OR/NOT gates on gene triggers) with a toehold-switch simulation
   - Ranked candidate list with scores, leakage, dynamic range, MFE, GC%, off-target specificity
   - Advanced filters (leakage limit, on/off ratio, max bp length)
   - Export GenBank/FASTA, or order plasmid synthesis through a partner (ships in 7 days)

## Design language
Clinical/lab aesthetic: warm off-white background, deep near-black primary, a single mint/red accent (oklch-based), Space Grotesk (display) + JetBrains Mono (mono/data), soft shadows, dashed-border upload zones, animated micro-icons per organism.

## Team & docs
- Multidisciplinary TAU student team: dry lab, wet lab, human practices
- Full project documentation (experiments, results, human practices, safety, engineering write-up) lives on the iGEM wiki: https://2025.igem.wiki/tau-israel
- Wiki source pages available: Project, Team, Description, Engineering, Experiments, Model, Results, Safety & Security, Software, Parts, Notebook, Human Practices, Entrepreneurship, Partners, Contributions, Attributions, Judging

## Status
v2.4.1, TAU iGEM Lab.
