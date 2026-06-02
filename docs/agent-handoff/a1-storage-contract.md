# A1 Storage Contract Handoff

## Scope

- Stage: P0.
- Slice: Storage Contract.
- Ownership: `src/grit_day_trading/storage.py` and `tests/test_storage_contract.py`.
- Canonical source: SQLite tables `import_batches`, `import_rows`, `orders`, `fills`, and `quarantine_rows`.

## Integrated Result

- Added `STORAGE_SCHEMA_VERSION = 1`.
- Added `storage_migrations` marker and `PRAGMA user_version`.
- Added unique indexes for file hash, import row hash, order idempotency, order business key, fill idempotency, fill execution key, fill source row, and quarantine source row.
- Added account canonicalization triggers for `import_rows`, `orders`, and `fills`.
- Kept the full P0 state-machine compatibility in main; A0 intentionally did not narrow `import_batches.status` to only `committed` and `failed`.

## Validation

- `python -m pytest -p no:cacheprovider tests/test_storage_contract.py -q` passed with `4 passed`.
- Main integration later passed `python -m pytest -q` with `24 passed`.

## Remaining Risk

- Existing legacy databases with conflicting duplicate data would need a repair migration before these unique indexes can be applied safely.

