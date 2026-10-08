# cernal (MATLAB client)

```matlab
addpath('/path/to/cernal_software/clients/matlab');

c   = cernal.Client(getenv('CERNAL_API_KEY'), 'BaseURL', 'https://your-cernal-host');
job = c.design('trigger_sequence', 'AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA', 'organism', 'ecoli');
T   = job.wait().results();          % a MATLAB table
head(T)

job = c.design('dge_csv', fileread('deseq2.csv'), ...
               'organism', 'ecoli', ...
               'gate_families', {'toehold'}, ...
               'constraints', struct('max_triggers', 1, 'min_separation', 1.0), ...
               'seed', 42);
T = job.wait().results();
writetable(T, 'candidates.csv');
job.artifact('fasta', 'best.fa');
```

`webwrite`/`webread`/`weboptions` — built into base MATLAB, no toolbox required. That
constraint is the point: a client needing the Bioinformatics Toolbox is a client half
the users cannot run. Name-value pairs, because that is how MATLAB reads, using the
same snake_case field names as the JSON API (`'trigger_sequence'`, not
`'TriggerSequence'`) — no translation layer to keep in sync. `struct` for nested
blocks (`constraints`, `scoring`, `budget`). Returns a `table`, so `writetable`,
`sortrows` and `groupsummary` work immediately.

There is no package manager worth targeting for a project like this; `addpath` is the
idiom. Ship the `+cernal` folder as-is.

`jsondecode` maps JSON objects to structs and silently mangles field names that are
not valid MATLAB identifiers — the nine metric names are all safe (`state_separation`,
`predicted_leakage`, ...), asserted in `tests/testCernal.m`.

**Not independently verified against a live server or a MATLAB/Octave interpreter** —
built directly from docs/public-api.md §11.3's spec and this repo's actual API
responses, but neither was available to run it. Per docs/public-api.md §11.4: *"A
licence in CI is not worth it for an iGEM team — say so plainly rather than pretending"*
— this client needs a manual run against a real deployment before a release, by
someone with MATLAB.

## Verification and result contracts (8 October 2026)

No package publication is claimed. Install from this repository's source; public
registry releases require separate maintainer authorization. Python HTTP conformance
and transport/ranking regressions execute against a local API. The R raw/table and
live HTTP conformance suite passed in [hosted Ubuntu CI](https://github.com/zivbental/cernal_software/actions/runs/37802426550/job/113397823314).
MATLAB runtime conformance remains unexecuted; its source changes are experimental.

Submission result options (`top_n`, `include_rejected`, `include_metrics`,
`include_artifacts`) remain on the job handle across queued completion. Persist them
when reconstructing a resumed handle; explicit results calls can override them.
Server-side `wait` is bounded to 0–300 seconds and submission transport timeout is
at least `wait + 10` seconds. Best-candidate helpers choose the lowest accepted rank
and return no result when all candidates are rejected or unranked.

Raw candidate JSON retains nested design, triggers, warnings and metrics. Flattened
tables are a separate convenience contract and are not compared to raw JSON column
sets. R exposes `cernal_candidates(job)` and MATLAB `job.rawCandidates()`.
