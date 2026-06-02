# A2 STP Parser Handoff

## Scope

- Stage: P0.
- Slice: STP Parser.
- Ownership: `src/grit_day_trading/parser.py`, parser tests, and parser fixtures.
- Canonical source: STP TXT raw rows.

## Integrated Result

- Current parser and field mapper versions are `stp_txt_parser_v0.3.1` and `stp_txt_mapping_v0.3.1`.
- Expanded STP field aliases for account, symbol, side, order id, execution id, quantity, price, timestamp, and status.
- Preserved physical raw line numbers after blank lines.
- Preserved mapping diagnostics, unknown columns, parser version, and field mapper version in parsed payload.
- Quarantined extra unmapped values instead of silently committing them.
- Added fallback idempotency basis metadata for fills missing execution id.
- Added `tests/fixtures/stp_edge_cases.tsv`.
- Added the no-header fill-only TXT contract: `日期、时间、标的、买卖、股数、价格、账号、通道`, optional 9th-column `order_id`, UTF-16 detection, synthetic timestamp, and row-hash fallback order id.
- Added parser paths for missing price quarantine, unsupported short no-header rows, cancel/order-only rows, partial fills, cross-day rows, and unknown tail columns.

## Validation

- Current main integration passed `python -m pytest -q` with `35 passed`.
- Current frontend contract validation passed `npm.cmd --prefix web run typecheck` and `npm.cmd --prefix web run build`.

## Remaining Risk

- Current fixtures are reference or simulated fixtures. Final parser acceptance still needs the first broker-original STP TXT sample.
