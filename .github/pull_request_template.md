<!--
Keep this short. Every question here exists because that mistake does NOT crash —
it produces a plausible number that quietly wins or loses the ranking.
-->

## What does this PR do?

<!-- One or two sentences, in plain language. Which pipeline step, which gate family? -->

🇮🇱 חדשים בגיטהאב? לפני שממלאים את הטופס הזה, קראו את `docs/onboarding.he.md` — שם מוסבר כל שלב.

---

## Checklist

**1. Which shared functions did you CALL instead of writing your own?**

<!-- List them. e.g. engine.sequences.reverse_complement, engine.stages.motifs.MotifScreener,
     engine.scoring.weighted_score, CandidateStore.mint_id, FoldEngine.mfe.
     If you wrote your own version of something that already exists, delete yours. -->

-

**2. Did you add or rename any metric name?**

The only nine names the scoring engine understands are:
`state_separation`, `trigger_accessibility`, `gate_folding_energy`, `predicted_leakage`,
`orthogonality`, `gc_content`, `dynamic_range`, `predicted_success_rate`, `circuit_complexity`.

Anything else you return is thrown away in silence, and the metric is then scored as if you
never measured it — which is the worst possible score. Nothing warns you.

- [ ] I return only names from that list, spelled exactly.
- [ ] If I added a new metric, this same PR also edits `src/engine/scoring/profiles.py`
      and bumps the profile version.

**3. For every number you return: what are its UNITS, and what happens when the measurement fails?**

<!-- Fill one line per metric: name — unit (kcal/mol? fraction 0-1? percent 0-100?
     linear fold-change or log2?) — what your code returns if the tool errors out. -->

| metric | unit | returns on failure |
| --- | --- | --- |
|  |  |  |

- [ ] When a measurement fails my code returns **`None`** — never `0`, never `0.0`.

> Why: `0.0` is a real, *perfect* score on several metrics. `predicted_leakage = 0.0` means
> "no leak at all" and passes every filter. `None` means "not measured" and is treated as the
> worst case. A `try/except: return 0.0` turns every design you could not measure into a
> flawless one that outranks the designs you measured correctly.

**4. Did you construct any shared tool yourself, with `()`?**

`FoldEngine`, `OffTargetScanner`, `MotifScreener`, `CodonOptimizer`, `TranslationScorer`,
`FoldProfiler` — these are built **once** in `pipeline.build_tools()` and handed to you.

- [ ] No. I did not write `FoldEngine(...)` or any of the others; I used the one I was given.
- [ ] I did not add `import RNA` to my file. (Only `engine/gates/tools/folding.py` and
      `engine/stages/folding.py` may import it.)

**5. Did the tests pass on your own machine?**

```
uv run pytest -q
```

- [ ] Yes, and I pasted the last line of the output below.

<!-- paste it here -->
