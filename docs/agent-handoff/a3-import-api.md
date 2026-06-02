# A3 Import API Handoff

## Scope

- Stage: P0.
- Slice: Import API service and tests.
- Ownership: `src/grit_day_trading/service.py` and `tests/test_import_api.py`.
- Read model: import batch, quarantine, fills, and daily summary API payloads.

## Integrated Result

- Unified public response shape for batches, quarantine rows, and fills.
- Added `batch_id`, `quarantine_id`, `raw_line`, `fill_id`, and `uses_fallback_idempotency_key` aliases.
- Fixed account and symbol filtering to avoid ambiguous SQL columns.
- Added fallback fill idempotency key with raw line hash for missing execution id.
- Added tests for list/detail contracts, duplicate upload, cross-batch normalized idempotency, fallback execution id, file-level failures, and 404/422 error contracts.

## Validation

- `python -m pytest -p no:cacheprovider tests/test_import_api.py -q` passed with `9 passed`.
- Main integration later passed API smoke with duplicate upload reusing the same batch.
- Main integration later passed `python -m pytest -q` with `24 passed`.

## Remaining Risk

- A0 did not add Pydantic response models yet; response shape is locked by tests rather than explicit FastAPI model classes.

