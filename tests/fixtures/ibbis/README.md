# Native cleared-result fixture

`mg1655-mcherry-native.json` is the unedited native JSON from the authorized
2026-10-16 real MG1655 heat-shock catalog / mCherry benchmark, Common Mechanism
2.1.0 (schema 0.6). SHA-256:
`8b21dacaca6de4949e1c3913845e8bca1b1c6cbff22349acff69f9a0f600de19`.

Source: local benchmark commit `ae4440b4fff7f55822808c5e6ce27fae7b356f34`,
`docs/evidence/ibbis-real-dataset-2026-10-16/native-output/result.output.json`.
The report contains annotations, not query or hazardous reference sequences.
The original run screened the complete 83-base switch and 958-base linear reporter
cassette; the native low-concern DNA match cleared a taxonomy match.

Tests use synthetic same-length placeholders to exercise parsing. These tests do
not screen those placeholders, create an operator deployment, or establish a
biological conclusion about any sequence. Mutated copies test failure handling;
the checked-in original is unchanged.

Pinned semantics:
- https://github.com/ibbis-bio/common-mechanism/blob/24fe0390978eb66d13db4f91c18f122d051b1a65/commec/config/result.py
- https://github.com/ibbis-bio/common-mechanism/blob/24fe0390978eb66d13db4f91c18f122d051b1a65/commec/screeners/check_low_concern.py
