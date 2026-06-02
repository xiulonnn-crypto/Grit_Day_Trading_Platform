# A2 STP Parser Handoff

## Scope

- Stage: P0.
- Slice: STP Parser.
- Ownership: `src/grit_day_trading/parser.py`, parser tests, and parser fixtures.
- Canonical source: STP TXT raw rows.

## Integrated Result

- Bumped parser and field mapper versions to `v0.2.0`.
- Expanded STP field aliases for account, symbol, side, order id, execution id, quantity, price, timestamp, and status.
- Preserved physical raw line numbers after blank lines.
- Preserved mapping diagnostics, unknown columns, parser version, and field mapper version in parsed payload.
- Quarantined extra unmapped values instead of silently committing them.
- Added fallback idempotency basis metadata for fills missing execution id.
- Added `tests/fixtures/stp_edge_cases.tsv`.

## Validation

- `python -m pytest -p no:cacheprovider tests/test_parser.py -q` passed with `7 passed`.
- Main integration later passed `python -m pytest -q` with `24 passed`.

## Remaining Risk

- Current fixtures are reference or simulated fixtures. Final parser acceptance still needs the first broker-original STP TXT sample.

