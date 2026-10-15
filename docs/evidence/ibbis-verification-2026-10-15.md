# Final-output screening software verification

Base: main `c1bb92cc085a6bad272298b81bda28c22b1d57f5`.
Branch: `dot/ibbis-final-output-screening`. No main merge or deployment.

Existing work inspected: merged #35 local safety protocol/policy, merged #79
sequence disclosure/download boundary, and draft #69 optional frontend screening
contract. This change reuses the backend boundaries and does not duplicate/merge
#69 or change scientific scoring/generation. All visible branch names were inspected;
no separate current IBBIS backend branch was identified. This is not a claim about
unpublished work.

## Final focused checks

- Adapter/native-schema/process/safety/API-surface focused run: 76 passed.
- Gate, API release disclosure, engine boundary and house rules: 762 passed in 40.45s.
- Dedicated coverage run: 177 passed in 40.51s. These counts overlap; do not add them.
- Independent review added real harmless sleeping-process descendant checks on CLI
  error exit, timeout and worker interruption: all three passed. One cleanup issue
  found during review was corrected before these checks.
- Ruff check and formatting passed; Django system check passed; migration drift check
  reported no changes; generated API surface was regenerated and its three checks pass.
- Full-repository suite is separate and was still running when this record was written;
  no full-suite pass is claimed here. Earlier in-progress runs during concurrent fixture
  edits are not final evidence. Exact-head CI results belong with the branch/PR.

All screening-positive/error/unknown fixtures are invented software reports. Harmless
repetitive strings and the existing benign integration fixture are used. No concerning
biological sequence corpus, real Common Mechanism database, or biological coverage
measurement was used.

## Software coverage (not biological coverage)

Measured with pytest-cov/coverage.py on Python 3.13.5 against only the two specified
modules; the JSON records exact covered/missing lines and branches.

- common_mechanism.py: 165/178 executable statements (92.70%); 53/64 branches (82.81%).
- safety.py: 298/313 executable statements (95.21%); 82/98 branches (83.67%).
- Combined: 463/491 statements (94.30%); 135/162 branches (83.33%).

The coverage tool's combined statement+branch display rounds to 92%; it is not a
92% biological detection rate. Missing software branches remain visible, not waived.

Reproduce:

```sh
UV_CACHE_DIR=/tmp/cernal-uv uv run --with pytest-cov pytest \
  tests/engine/test_common_mechanism.py tests/engine/test_commec_process_cleanup.py \
  tests/engine/test_safety_screening.py tests/api/test_release_disclosure.py \
  --cov=engine.common_mechanism --cov=engine.safety --cov-branch \
  --cov-report=json:docs/evidence/ibbis-test-coverage-2026-10-15.json \
  --cov-report=term-missing -q
```

The transient test environment does not change uv.lock or application dependencies.
See `ibbis-overhead-2026-10-15.json` and `../ibbis-final-screening-benchmarks.md` for
synthetic timing/memory raw samples and the separate, unexecuted real-tool protocol.
See `../ibbis-final-output-screening.md` for operator trust, policy, resource and licensing
limits. These measurements do not select or authorize a production release policy.
