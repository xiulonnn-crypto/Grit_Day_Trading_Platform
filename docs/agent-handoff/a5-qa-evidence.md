# A5 QA / Evidence Handoff

## Scope

- Stage: P0.
- Slice: QA / Evidence.
- Ownership: fixture files, `tests/test_e2e_p0.py`, and `docs/p0_acceptance.md`.

## Integrated Result

- Added P0 edge fixture covering partial fill, missing execution id fallback, cancel order, cross-day fill, unknown column, and missing price quarantine.
- Added missing-required fixture covering failed batch paths without committed fills.
- Added DB/API/UI read-model consistency tests.
- Added negative acceptance tests for empty files and missing required fields.
- Converted the original strict `xfail` for `GET /api/imports` `batch_id` alias into a hard passing contract after A3 fixed the read model.
- Updated [docs/p0_acceptance.md](../p0_acceptance.md) with PASS status for the batch-list alias.

## Validation

- Main integration passed `python -m pytest -q` with `24 passed`.
- Main API smoke observed duplicate upload reuse, `fills=3`, `quarantine=1`, and `summary_source=committed_fills_only`.

## Remaining Risk

- No verified broker-original STP TXT sample is present yet.
- Browser DOM/screenshot acceptance was not run for this cleanup slice.

