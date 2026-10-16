# Contributing to CERNAL

Start with [architecture](docs/architecture.md), [current status](docs/status.md),
[development setup](docs/development.md), and [testing](docs/testing.md).
[CLAUDE.md](CLAUDE.md) contains repository-specific implementation rules for coding assistants.

## Make one reviewable change

1. Start a branch from the intended current base and record its commit.
2. Inspect existing implementations before adding parallel tools or scientific formulas.
3. Keep the engine framework-free; platform imports only `engine.contract` and `engine.client`.
4. Add regression tests for changed contracts and preserve explicit missing measurements;
   failed computation must not become a perfect numeric score.
5. Update the relevant active guide and versioned capability/metric contract when applicable.
6. Run the checks documented in [testing](docs/testing.md), recording passed, failed and
   not-run checks separately. Submit review with evidence and remaining limits.

## Documentation and scientific evidence

Use [the documentation index](docs/README.md) to choose one authoritative home for a topic.
Do not add a second competing setup, API or status guide. Keep research branches explicitly
branch-only and pin their commit; only merged capabilities belong in the current guide.
Record scientific methods, units, dataset/reference versions, assumptions, raw evidence and
limits. Test counts and timings are observations at a revision, never permanent guarantees.

Preserve data, notebooks, unique rationale, attribution and provenance. Superseded narrative
belongs in the [archive](docs/archive/README.md), with a link from its replacement and an entry
in the [source inventory](docs/evidence/documentation-inventory.md). Do not erase raw results
because their interpretation changed; mark them superseded and explain the corrected method.
Never publish credentials or private human data in documentation or test artifacts.

Regenerate [API surface](docs/api-surface.md) through `tools/gen_api_surface.py`; don't hand-edit
its generated contracts. Use numbered [ADRs](docs/decisions/) for costly architectural changes.
[Attribution](docs/attribution.md) and [release decisions](docs/release-decisions.md) require
human review. A code review does not authorize production deployment or biological claims.
