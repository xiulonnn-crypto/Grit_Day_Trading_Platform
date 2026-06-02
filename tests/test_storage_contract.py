import sqlite3

import pytest

from grit_day_trading.storage import STORAGE_SCHEMA_VERSION, connect, initialize_database


def test_storage_contract_creates_required_indexes_triggers_and_migration_marker(tmp_path):
    conn = connect(tmp_path / "trading.db")
    try:
        initialize_database(conn)

        assert conn.execute("PRAGMA user_version").fetchone()[0] == STORAGE_SCHEMA_VERSION
        migration = conn.execute(
            "SELECT description FROM storage_migrations WHERE version = ?",
            (STORAGE_SCHEMA_VERSION,),
        ).fetchone()
        assert migration["description"] == "p0_storage_contract_v1"
        assert {
            "ux_import_batches_file_hash",
            "ux_import_rows_batch_line_hash",
            "ux_orders_idempotency_key",
            "ux_orders_account_order",
        }.issubset(_index_names(conn, "orders") | _index_names(conn, "import_batches") | _index_names(conn, "import_rows"))
        assert {
            "ux_fills_idempotency_key",
            "ux_fills_account_execution",
            "ux_fills_source_import_row",
            "ux_quarantine_import_row",
        }.issubset(_index_names(conn, "fills") | _index_names(conn, "quarantine_rows"))
        assert {
            "trg_import_rows_account_canonical_insert",
            "trg_orders_account_canonical_insert",
            "trg_fills_account_canonical_insert",
        }.issubset(_trigger_names(conn))
    finally:
        conn.close()


def test_storage_contract_rejects_non_canonical_account_fields(tmp_path):
    conn = connect(tmp_path / "trading.db")
    try:
        initialize_database(conn)
        _insert_batch(conn)
        _insert_import_row(conn, row_id="row_1", raw_line_number=1, order_id="O-1", execution_id="E-1")
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError, match="account_canonical_mismatch"):
            _insert_order(
                conn,
                record_id="order_bad",
                source_row_id="row_1",
                account_raw=" acct-01 \n",
                account_canonical="acct-01",
                order_id="O-1",
                idempotency_key="bad-order-key",
            )
        conn.rollback()

        with pytest.raises(sqlite3.IntegrityError, match="account_canonical_mismatch"):
            _insert_fill(
                conn,
                record_id="fill_bad",
                source_row_id="row_1",
                account_raw="\tacct-01 ",
                account_canonical="ACCT_01",
                execution_id="E-1",
                idempotency_key="bad-fill-key",
            )
    finally:
        conn.close()


def test_storage_contract_blocks_duplicate_order_and_fill_business_keys(tmp_path):
    conn = connect(tmp_path / "trading.db")
    try:
        initialize_database(conn)
        _insert_batch(conn)
        _insert_import_row(conn, row_id="row_1", raw_line_number=1, order_id="O-1", execution_id="E-1")
        _insert_import_row(conn, row_id="row_2", raw_line_number=2, order_id="O-1", execution_id="E-1")
        _insert_import_row(conn, row_id="row_3", raw_line_number=3, order_id="O-2", execution_id="E-1")
        conn.commit()

        _insert_order(
            conn,
            record_id="order_1",
            source_row_id="row_1",
            account_raw=" acct-01 ",
            account_canonical="ACCT-01",
            order_id="O-1",
            idempotency_key="order-key-1",
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            _insert_order(
                conn,
                record_id="order_2",
                source_row_id="row_2",
                account_raw="acct-01",
                account_canonical="ACCT-01",
                order_id="O-1",
                idempotency_key="order-key-2",
            )
        conn.rollback()

        _insert_fill(
            conn,
            record_id="fill_1",
            source_row_id="row_1",
            account_raw=" acct-01 ",
            account_canonical="ACCT-01",
            execution_id="E-1",
            idempotency_key="fill-key-1",
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            _insert_fill(
                conn,
                record_id="fill_2",
                source_row_id="row_3",
                account_raw="acct-01",
                account_canonical="ACCT-01",
                execution_id="E-1",
                idempotency_key="fill-key-2",
            )
    finally:
        conn.close()


def test_initialize_database_migrates_legacy_schema_with_contract_indexes(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy.db")
    conn.row_factory = sqlite3.Row
    try:
        _create_legacy_schema(conn)
        _insert_batch(conn)
        _insert_import_row(conn, row_id="row_1", raw_line_number=1, order_id="O-1", execution_id="E-1")
        conn.commit()

        initialize_database(conn)

        assert conn.execute("PRAGMA user_version").fetchone()[0] == STORAGE_SCHEMA_VERSION
        assert "ux_import_batches_file_hash" in _index_names(conn, "import_batches")
        with pytest.raises(sqlite3.IntegrityError, match="account_canonical_mismatch"):
            _insert_order(
                conn,
                record_id="order_bad",
                source_row_id="row_1",
                account_raw=" acct-01 ",
                account_canonical="acct-01",
                order_id="O-1",
                idempotency_key="bad-order-key",
            )
    finally:
        conn.close()


def _index_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA index_list({table_name})").fetchall()}


def _trigger_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall()
    return {row["name"] for row in rows}


def _insert_batch(conn: sqlite3.Connection, batch_id: str = "batch_1", file_hash: str = "hash_1") -> None:
    conn.execute(
        """
        INSERT INTO import_batches (
            id, file_name, file_hash, uploaded_at, parser_version, field_mapper_version,
            status, status_reason, row_count, accepted_rows, quarantined_rows
        ) VALUES (?, 'sample.tsv', ?, '2026-06-01T09:30:00Z', 'parser_v1', 'mapper_v1',
            'committed', NULL, 1, 1, 0)
        """,
        (batch_id, file_hash),
    )


def _insert_import_row(
    conn: sqlite3.Connection,
    *,
    row_id: str,
    raw_line_number: int,
    order_id: str,
    execution_id: str,
) -> None:
    conn.execute(
        """
        INSERT INTO import_rows (
            id, batch_id, raw_line_number, raw_text, raw_line_hash, parser_version,
            field_mapper_version, account_raw, account_canonical, parsed_payload_json,
            row_status, order_id, execution_id
        ) VALUES (?, 'batch_1', ?, ?, ?, 'parser_v1', 'mapper_v1',
            ' acct-01 ', 'ACCT-01', '{}', 'accepted', ?, ?)
        """,
        (row_id, raw_line_number, f"raw-{raw_line_number}", f"hash-{raw_line_number}", order_id, execution_id),
    )


def _insert_order(
    conn: sqlite3.Connection,
    *,
    record_id: str,
    source_row_id: str,
    account_raw: str,
    account_canonical: str,
    order_id: str,
    idempotency_key: str,
) -> None:
    conn.execute(
        """
        INSERT INTO orders (
            id, account_raw, account_canonical, symbol, side, order_id, order_status,
            submitted_at, source_batch_id, source_import_row_id, idempotency_key
        ) VALUES (?, ?, ?, 'NVDA', 'BUY', ?, 'FILLED',
            '2026-06-01T09:30:00Z', 'batch_1', ?, ?)
        """,
        (record_id, account_raw, account_canonical, order_id, source_row_id, idempotency_key),
    )


def _insert_fill(
    conn: sqlite3.Connection,
    *,
    record_id: str,
    source_row_id: str,
    account_raw: str,
    account_canonical: str,
    execution_id: str,
    idempotency_key: str,
) -> None:
    conn.execute(
        """
        INSERT INTO fills (
            id, account_raw, account_canonical, symbol, side, order_id, execution_id,
            filled_at, quantity, price, source_batch_id, source_import_row_id, idempotency_key
        ) VALUES (?, ?, ?, 'NVDA', 'BUY', 'O-1', ?,
            '2026-06-01T09:30:00Z', 10, 100.5, 'batch_1', ?, ?)
        """,
        (record_id, account_raw, account_canonical, execution_id, source_row_id, idempotency_key),
    )


def _create_legacy_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE import_batches (
            id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            field_mapper_version TEXT NOT NULL,
            status TEXT NOT NULL,
            status_reason TEXT,
            row_count INTEGER NOT NULL DEFAULT 0,
            accepted_rows INTEGER NOT NULL DEFAULT 0,
            quarantined_rows INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE import_rows (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
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
            fill_record_id TEXT
        );

        CREATE TABLE orders (
            id TEXT PRIMARY KEY,
            account_raw TEXT NOT NULL,
            account_canonical TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            order_id TEXT NOT NULL,
            order_status TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            source_batch_id TEXT NOT NULL,
            source_import_row_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL
        );

        CREATE TABLE fills (
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
            source_batch_id TEXT NOT NULL,
            source_import_row_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL
        );

        CREATE TABLE quarantine_rows (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            import_row_id TEXT,
            raw_line_number INTEGER NOT NULL,
            raw_text TEXT NOT NULL,
            failed_field TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            reason TEXT NOT NULL,
            repair_hint TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'open'
        );
        """
    )
