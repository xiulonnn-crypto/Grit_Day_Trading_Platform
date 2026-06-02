from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


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
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def dumps_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
