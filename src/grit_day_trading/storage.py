from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


STORAGE_SCHEMA_VERSION = 1
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
    conn.executescript(STORAGE_CONTRACT_SQL)
    conn.execute(
        """
        INSERT OR IGNORE INTO storage_migrations (version, description)
        VALUES (?, ?)
        """,
        (STORAGE_SCHEMA_VERSION, "p0_storage_contract_v1"),
    )
    conn.execute(f"PRAGMA user_version = {STORAGE_SCHEMA_VERSION}")
    conn.commit()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def dumps_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
