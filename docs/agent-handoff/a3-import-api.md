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
- Added replay support for old zero-row file-level failed batches when parser or mapper versions drift.
- Added rebuild support for old committed batches when parser or mapper versions drift.
- Added committed fill read-model dedupe across changed-hash fallback batches while preserving same-file duplicate raw rows.
- Added round-trip daily summary logic for PnL, win rate, profit factor, and paired traded quantity.

## Validation

- Current main integration passed `python -m pytest -q` with `35 passed`.
- Current frontend contract validation passed `npm.cmd --prefix web run typecheck` and `npm.cmd --prefix web run build`.

## Remaining Risk

- A0 did not add Pydantic response models yet; response shape is locked by tests rather than explicit FastAPI model classes.
