# CERNAL documentation

CERNAL turns transcript-derived signals into ranked **computational RNA-control candidates**.
It helps researchers inspect design choices and retain provenance; it does not establish that a
construct will work experimentally. This guide describes the main baseline pinned in
[status](status.md), with ongoing work identified separately.

## Read by goal

| Goal | Reading path |
|---|---|
| Understand the product | [Root overview](../README.md) → [capabilities and status](status.md) → [modalities](modalities.md) |
| Try a supported workflow | [Install](development.md) → [tutorial](tutorial.md) → [interpret results](scientific-interpretation.md) |
| Understand methods | [Engine](engine.md) → [genes](genes.md) → [trigger selection](triggers.md) → [window methods](window-selection-procedure.md) → [assembly](plasmids.md) |
| Reproduce scientific evidence | [Evidence guide](evidence/README.md) → [trigger logbook](trigger-selection-development-logbook.md) → [reference datasets](public-datasets.md) |
| Write an integration | [Public API/client guide](public-api.md) → [endpoint reference](api.md) → [generated API surface](api-surface.md) → [domain model](domain-model.md) |
| Operate a deployment | [Configuration](configuration.md) → [deployment](deployment.md) → [operations](operations.md) → [security](security.md) |
| Change the software | [Contributing](../CONTRIBUTING.md) → [architecture](architecture.md) → [testing](testing.md) → [ADRs](decisions/) |
| Assess readiness | [Status](status.md) → [limitations/roadmap](ROADMAP.md) → [release decisions](release-decisions.md) → [attribution](attribution.md) |

## Merged workflows

- [Eukaryotic two-input AND](and-gate.md): Human/yeast DE workflow, evidence and limitations
- [Screening-status UI](sequence-screening.md): optional evidence contract, not an operational adapter

## Scientific references

- [NucSyn design inputs and attribution](nucsyn.md): upstream credit, research CSV contract, reproducibility and runtime boundary

- [Scientific interpretation](scientific-interpretation.md): definitions, units and what scores cannot prove
- [Trigger/nucleation ranking](trigger-nucleation-ranking.md): ranking modes and provenance
- [Off-target analysis](off-target-analysis.md): computational scope and specificity limits
- [Catalog governance](catalog-governance.md), [public datasets](public-datasets.md) and [collaborations](collaborations.md)
- [Integration](integration.md): scientific components versus the production execution path
- [CRISPR workbench (Hebrew)](crispr-workbench.he.md) and [implementation reference (Hebrew)](crispr-implementation.he.md): research tools, not production capabilities
- [Notebook directory](../src/engine/gates/notebooks/README.md): offline experiments; [status](status.md) distinguishes merged application support from research branches

## Where truth lives

Source and tests define implementation. `/api/version` describes the installed build's
supported application choices. [Status](status.md) is a dated, commit-pinned snapshot,
[ROADMAP](ROADMAP.md) contains unresolved work, and [evidence](evidence/README.md) records
what was actually measured. These are different questions; a passing test is not an
experimental result and a branch implementation is not a merged capability.

Signed-in user help lives at `/use-cases`, `/guide` and `/faq` in the React application;
[user-help.md](user-help.md) maps its source. This Markdown network renders directly on
GitHub; no documentation server is required.

## History, data and maintenance

The [archive](archive/README.md) contains superseded plans and dated audits. The
[development log](software-development-log.md) and [scientific logbook](trigger-selection-development-logbook.md)
retain chronology, while primary guides describe current behavior. Original data, notebooks,
figures and manifests remain available. [Inventory](evidence/documentation-inventory.md)
records where each original documentation source went.

Keep links relative, put new scientific claims beside evidence, pin external branch claims,
and update the relevant active guide with a code change. Never copy a historical performance
number into a current guarantee. New architectural trade-offs belong in [ADRs](decisions/).
