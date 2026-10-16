# Limitations and next work

Current baseline and pending branches: [status](status.md). This page records unresolved
outcomes, not an assertion that old backlog entries remain unimplemented.

## Scientific acceptance

- Calibrate ranking weights, leakage, accessibility and binding heuristics against independent
  measurements. Software regression tests cannot establish biological efficacy.
- Define and validate transcriptome-wide off-target specificity, relevant isoforms, biological
  context and concentration assumptions. [Off-target scope](off-target-analysis.md).
- Review reference mapping and public-data contrasts with the scientific/data owners.
  [Dataset governance](catalog-governance.md).
- Integrate multi-input/AND functionality only after its application contract, supported hosts,
  correctness tests and scientific limitations agree. Open PRs are pinned in [status](status.md).
- Corrected barrier work needs complete reproducible row-level evidence at its published head;
  endpoint-energy differences must not be interpreted as path barriers.

## Operational acceptance

- Validate screening executable/database provenance, full final-construct coverage, failure
  modes and measured resource requirements before activating a release adapter.
- Complete deployment-specific security, backup/restore and queued-worker acceptance.
  A repository service file does not prove an operating service.
- Confirm human-data governance, retention, account policy and responsible owners before
  public uploads; resolve [release decisions](release-decisions.md).
- Verify dedicated iGEM GitLab software hosting with the exact namespace, matching commit
  and pipeline evidence. Verify attribution and asset permissions with the team.
- Run native MATLAB conformance before describing it as verified. Registry publication and
  synthesis ordering require separate release decisions; neither is implied by source clients.

## How work becomes current

For a feature, record the merged commit, capability changes, tests and unresolved limits;
then update its active guide and [status](status.md). For a scientific claim, retain input
provenance, method/version, raw results and independent validation as appropriate. For an
operational claim, retain evidence from the actual environment, not just configuration.

The previous long backlog, closed questions, timings and design deliberations are retained
in the [historical roadmap](archive/records/ROADMAP.md). They are evidence of earlier plans,
not today's task list. [Contributing](../CONTRIBUTING.md) explains documentation updates.
