from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


STORAGE_SCHEMA_VERSION = 5
ACCOUNT_STRIP_CHARS_SQL = "char(9) || char(10) || char(11) || char(12) || char(13) || char(32)"


def _account_canonical_expr(column: str) -> str:
    return f"upper(trim({column}, {ACCOUNT_STRIP_CHARS_SQL}))"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS import_batches (
    id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    parser_version TEXT NOT NULL,
    field_mapper_version TEXT NOT NULL,
    status TEXT NOT NULL,
    status_reason TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    accepted_rows INTEGER NOT NULL DEFAULT 0,
    quarantined_rows INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS import_rows (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    raw_line_number INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    raw_line_hash TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    field_mapper_version TEXT NOT NULL,
    account_raw TEXT,
    account_canonical TEXT,
    parsed_payload_json TEXT NOT NULL,
    row_status TEXT NOT NULL,
    order_id TEXT,
    execution_id TEXT,
    order_record_id TEXT,
    fill_record_id TEXT,
    UNIQUE(batch_id, raw_line_number, raw_line_hash)
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    account_raw TEXT NOT NULL,
    account_canonical TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_id TEXT NOT NULL,
    order_status TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    source_batch_id TEXT NOT NULL REFERENCES import_batches(id),
    source_import_row_id TEXT NOT NULL REFERENCES import_rows(id),
    idempotency_key TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS fills (
    id TEXT PRIMARY KEY,
    account_raw TEXT NOT NULL,
    account_canonical TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_id TEXT NOT NULL,
    execution_id TEXT,
    filled_at TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    source_batch_id TEXT NOT NULL REFERENCES import_batches(id),
    source_import_row_id TEXT NOT NULL REFERENCES import_rows(id),
    idempotency_key TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS quarantine_rows (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    import_row_id TEXT REFERENCES import_rows(id) ON DELETE CASCADE,
    raw_line_number INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    failed_field TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason TEXT NOT NULL,
    repair_hint TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS storage_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_data_provider_attempts (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    request_type TEXT NOT NULL,
    requested_start TEXT NOT NULL,
    requested_end TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'partial', 'missing', 'failed', 'timezone_conflict')),
    error_code TEXT,
    payload_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS market_context_snapshots (
    id TEXT PRIMARY KEY,
    fill_id TEXT NOT NULL REFERENCES fills(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    requested_start TEXT NOT NULL,
    requested_end TEXT NOT NULL,
    provider_timezone TEXT NOT NULL,
    bar_count INTEGER NOT NULL DEFAULT 0,
    bars_hash TEXT NOT NULL,
    bars_json TEXT NOT NULL,
    vwap REAL,
    day_high REAL,
    day_low REAL,
    volume_context TEXT NOT NULL,
    data_status TEXT NOT NULL CHECK (
        data_status IN ('available', 'partial', 'missing', 'provider_failed', 'timezone_conflict')
    ),
    failure_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(fill_id, provider, requested_start, requested_end)
);

CREATE TABLE IF NOT EXISTS market_minute_archives (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    requested_start TEXT NOT NULL,
    requested_end TEXT NOT NULL,
    provider_timezone TEXT NOT NULL,
    bar_count INTEGER NOT NULL DEFAULT 0,
    bars_hash TEXT NOT NULL,
    bars_json TEXT NOT NULL,
    vwap REAL,
    day_high REAL,
    day_low REAL,
    volume_context TEXT NOT NULL,
    data_status TEXT NOT NULL CHECK (
        data_status IN ('available', 'partial', 'missing', 'provider_failed', 'timezone_conflict')
    ),
    failure_reason TEXT,
    source_fill_count INTEGER NOT NULL DEFAULT 0,
    archive_version TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(provider, symbol, trade_date, requested_start, requested_end)
);

CREATE TABLE IF NOT EXISTS watchlist_runs (
    id TEXT PRIMARY KEY,
    trade_date TEXT NOT NULL,
    provider TEXT NOT NULL,
    rules_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    item_count INTEGER NOT NULL DEFAULT 0,
    failure_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(trade_date, provider, rules_version)
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES watchlist_runs(id) ON DELETE CASCADE,
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    rank INTEGER NOT NULL,
    reason_codes_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('included', 'missing', 'provider_failed')),
    UNIQUE(run_id, symbol)
);

CREATE TABLE IF NOT EXISTS strategy_configs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    template_key TEXT NOT NULL,
    template_version TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    params_json TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS strategy_signal_runs (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES strategy_configs(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    source_archive_id TEXT REFERENCES market_minute_archives(id) ON DELETE SET NULL,
    bars_hash TEXT NOT NULL DEFAULT '',
    params_hash TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    indicator_engine_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'completed',
            'missing_archive',
            'non_available_archive',
            'insufficient_bars',
            'strategy_disabled',
            'failed'
        )
    ),
    failure_reason TEXT,
    indicator_series_json TEXT NOT NULL DEFAULT '[]',
    indicator_hash TEXT NOT NULL DEFAULT '',
    signal_count INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS strategy_signals (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES strategy_signal_runs(id) ON DELETE CASCADE,
    timestamp TEXT NOT NULL,
    bar_index INTEGER NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    action TEXT NOT NULL CHECK (action IN ('ENTRY_LONG', 'EXIT_LONG', 'ENTRY_SHORT', 'EXIT_SHORT')),
    price REAL NOT NULL,
    stop_loss_price REAL,
    take_profit_price REAL,
    linked_entry_signal_id TEXT REFERENCES strategy_signals(id) ON DELETE SET NULL,
    reason_codes_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_test_batches (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES strategy_configs(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    end_date TEXT NOT NULL,
    window_trading_days INTEGER NOT NULL,
    archive_scope_hash TEXT NOT NULL,
    params_json TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    template_version TEXT NOT NULL,
    indicator_engine_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('completed', 'insufficient_archive_coverage', 'strategy_disabled', 'failed')
    ),
    failure_reason TEXT,
    day_count INTEGER NOT NULL DEFAULT 0,
    available_day_count INTEGER NOT NULL DEFAULT 0,
    completed_day_count INTEGER NOT NULL DEFAULT 0,
    signal_count INTEGER NOT NULL DEFAULT 0,
    total_pnl REAL NOT NULL DEFAULT 0,
    win_rate REAL NOT NULL DEFAULT 0,
    profit_factor REAL,
    max_drawdown REAL NOT NULL DEFAULT 0,
    coverage_ratio REAL NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS strategy_test_day_results (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES strategy_test_batches(id) ON DELETE CASCADE,
    trade_date TEXT NOT NULL,
    source_archive_id TEXT REFERENCES market_minute_archives(id) ON DELETE SET NULL,
    bars_hash TEXT NOT NULL DEFAULT '',
    strategy_run_id TEXT REFERENCES strategy_signal_runs(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'completed',
            'missing_archive',
            'non_available_archive',
            'insufficient_bars',
            'strategy_disabled',
            'failed'
        )
    ),
    failure_reason TEXT,
    signal_count INTEGER NOT NULL DEFAULT 0,
    total_pnl REAL NOT NULL DEFAULT 0,
    win_rate REAL NOT NULL DEFAULT 0,
    profit_factor REAL,
    closed_group_count INTEGER NOT NULL DEFAULT 0,
    indicator_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(batch_id, trade_date)
);

CREATE TABLE IF NOT EXISTS strategy_optimization_runs (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES strategy_configs(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    end_date TEXT NOT NULL,
    window_trading_days INTEGER NOT NULL,
    archive_scope_hash TEXT NOT NULL,
    search_space_json TEXT NOT NULL,
    search_space_hash TEXT NOT NULL,
    objective TEXT NOT NULL,
    template_version TEXT NOT NULL,
    indicator_engine_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('completed', 'insufficient_archive_coverage', 'strategy_disabled', 'failed')
    ),
    failure_reason TEXT,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    eligible_candidate_count INTEGER NOT NULL DEFAULT 0,
    best_candidate_id TEXT,
    best_params_hash TEXT,
    best_stability_score REAL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS strategy_optimization_candidates (
    id TEXT PRIMARY KEY,
    optimization_run_id TEXT NOT NULL REFERENCES strategy_optimization_runs(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    params_json TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    day_results_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('eligible', 'no_signals', 'failed', 'insufficient_archive_coverage', 'strategy_disabled')
    ),
    failure_reason TEXT,
    total_pnl REAL NOT NULL DEFAULT 0,
    win_rate REAL NOT NULL DEFAULT 0,
    profit_factor REAL,
    max_drawdown REAL NOT NULL DEFAULT 0,
    closed_group_count INTEGER NOT NULL DEFAULT 0,
    coverage_ratio REAL NOT NULL DEFAULT 0,
    stability_score REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(optimization_run_id, params_hash)
);
"""

STORAGE_CONTRACT_SQL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS ux_import_batches_file_hash
ON import_batches(file_hash);

CREATE UNIQUE INDEX IF NOT EXISTS ux_import_rows_batch_line_hash
ON import_rows(batch_id, raw_line_number, raw_line_hash);

CREATE UNIQUE INDEX IF NOT EXISTS ux_orders_idempotency_key
ON orders(idempotency_key);

CREATE UNIQUE INDEX IF NOT EXISTS ux_orders_account_order
ON orders(account_canonical, order_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_fills_idempotency_key
ON fills(idempotency_key);

CREATE UNIQUE INDEX IF NOT EXISTS ux_fills_account_execution
ON fills(account_canonical, execution_id)
WHERE execution_id IS NOT NULL AND execution_id <> '';

CREATE UNIQUE INDEX IF NOT EXISTS ux_fills_source_import_row
ON fills(source_import_row_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_quarantine_import_row
ON quarantine_rows(import_row_id)
WHERE import_row_id IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_import_rows_account_canonical_insert
BEFORE INSERT ON import_rows
FOR EACH ROW
WHEN NOT (
    (NEW.account_raw IS NULL AND NEW.account_canonical IS NULL)
    OR (
        NEW.account_raw IS NOT NULL
        AND NEW.account_canonical = {_account_canonical_expr("NEW.account_raw")}
    )
)
BEGIN
    SELECT RAISE(ABORT, 'account_canonical_mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_import_rows_account_canonical_update
BEFORE UPDATE OF account_raw, account_canonical ON import_rows
FOR EACH ROW
WHEN NOT (
    (NEW.account_raw IS NULL AND NEW.account_canonical IS NULL)
    OR (
        NEW.account_raw IS NOT NULL
        AND NEW.account_canonical = {_account_canonical_expr("NEW.account_raw")}
    )
)
BEGIN
    SELECT RAISE(ABORT, 'account_canonical_mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_orders_account_canonical_insert
BEFORE INSERT ON orders
FOR EACH ROW
WHEN NEW.account_raw IS NULL
    OR NEW.account_canonical IS NULL
    OR NEW.account_canonical <> {_account_canonical_expr("NEW.account_raw")}
BEGIN
    SELECT RAISE(ABORT, 'account_canonical_mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_orders_account_canonical_update
BEFORE UPDATE OF account_raw, account_canonical ON orders
FOR EACH ROW
WHEN NEW.account_raw IS NULL
    OR NEW.account_canonical IS NULL
    OR NEW.account_canonical <> {_account_canonical_expr("NEW.account_raw")}
BEGIN
    SELECT RAISE(ABORT, 'account_canonical_mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_fills_account_canonical_insert
BEFORE INSERT ON fills
FOR EACH ROW
WHEN NEW.account_raw IS NULL
    OR NEW.account_canonical IS NULL
    OR NEW.account_canonical <> {_account_canonical_expr("NEW.account_raw")}
BEGIN
    SELECT RAISE(ABORT, 'account_canonical_mismatch');
END;

CREATE TRIGGER IF NOT EXISTS trg_fills_account_canonical_update
BEFORE UPDATE OF account_raw, account_canonical ON fills
FOR EACH ROW
WHEN NEW.account_raw IS NULL
    OR NEW.account_canonical IS NULL
    OR NEW.account_canonical <> {_account_canonical_expr("NEW.account_raw")}
BEGIN
    SELECT RAISE(ABORT, 'account_canonical_mismatch');
END;

CREATE INDEX IF NOT EXISTS ix_market_attempts_symbol_created
ON market_data_provider_attempts(provider, symbol, request_type, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS ux_market_context_snapshot_window
ON market_context_snapshots(fill_id, provider, requested_start, requested_end);

CREATE INDEX IF NOT EXISTS ix_market_context_symbol_created
ON market_context_snapshots(symbol, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS ux_market_minute_archive_window
ON market_minute_archives(provider, symbol, trade_date, requested_start, requested_end);

CREATE UNIQUE INDEX IF NOT EXISTS ux_market_minute_archive_idempotency
ON market_minute_archives(idempotency_key);

CREATE INDEX IF NOT EXISTS ix_market_minute_archive_date_symbol
ON market_minute_archives(trade_date, symbol);

CREATE UNIQUE INDEX IF NOT EXISTS ux_watchlist_run_contract
ON watchlist_runs(trade_date, provider, rules_version);

CREATE UNIQUE INDEX IF NOT EXISTS ux_watchlist_items_run_symbol
ON watchlist_items(run_id, symbol);

CREATE INDEX IF NOT EXISTS ix_watchlist_items_date_rank
ON watchlist_items(trade_date, rank);

CREATE INDEX IF NOT EXISTS ix_strategy_configs_template_enabled
ON strategy_configs(template_key, enabled);

CREATE UNIQUE INDEX IF NOT EXISTS ux_strategy_signal_run_idempotency
ON strategy_signal_runs(idempotency_key);

CREATE INDEX IF NOT EXISTS ix_strategy_signal_runs_lookup
ON strategy_signal_runs(trade_date, symbol, strategy_id, created_at);

CREATE INDEX IF NOT EXISTS ix_strategy_signals_run_time
ON strategy_signals(run_id, timestamp, bar_index);

CREATE UNIQUE INDEX IF NOT EXISTS ux_strategy_test_batch_idempotency
ON strategy_test_batches(idempotency_key);

CREATE INDEX IF NOT EXISTS ix_strategy_test_batches_lookup
ON strategy_test_batches(end_date, symbol, strategy_id, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS ux_strategy_test_day_batch_date
ON strategy_test_day_results(batch_id, trade_date);

CREATE INDEX IF NOT EXISTS ix_strategy_test_day_results_run
ON strategy_test_day_results(strategy_run_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_strategy_optimization_idempotency
ON strategy_optimization_runs(idempotency_key);

CREATE INDEX IF NOT EXISTS ix_strategy_optimization_lookup
ON strategy_optimization_runs(end_date, symbol, strategy_id, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS ux_strategy_optimization_candidate_params
ON strategy_optimization_candidates(optimization_run_id, params_hash);

CREATE INDEX IF NOT EXISTS ix_strategy_optimization_candidate_rank
ON strategy_optimization_candidates(optimization_run_id, rank);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    _ensure_compatible_columns(conn)
    conn.executescript(STORAGE_CONTRACT_SQL)
    conn.execute(
        """
        INSERT OR IGNORE INTO storage_migrations (version, description)
        VALUES (?, ?)
        """,
        (1, "p0_storage_contract_v1"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO storage_migrations (version, description)
        VALUES (?, ?)
        """,
        (2, "p1_market_context_contract_v2"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO storage_migrations (version, description)
        VALUES (?, ?)
        """,
        (3, "p1_yahoo_minute_archive_contract_v3"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO storage_migrations (version, description)
        VALUES (?, ?)
        """,
        (4, "p2_strategy_signal_contract_v4"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO storage_migrations (version, description)
        VALUES (?, ?)
        """,
        (5, "p2_strategy_testing_optimization_contract_v5"),
    )
    conn.execute(f"PRAGMA user_version = {STORAGE_SCHEMA_VERSION}")
    conn.commit()


def _ensure_compatible_columns(conn: sqlite3.Connection) -> None:
    strategy_run_columns = _table_columns(conn, "strategy_signal_runs")
    if "params_json" not in strategy_run_columns:
        conn.execute("ALTER TABLE strategy_signal_runs ADD COLUMN params_json TEXT NOT NULL DEFAULT '{}'")


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def dumps_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
