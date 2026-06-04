import hashlib
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from grit_day_trading.api import create_app
from grit_day_trading.parser import FIELD_MAPPER_VERSION, PARSER_VERSION
from grit_day_trading.storage import connect, initialize_database


SAMPLE_PATH = Path("tests/fixtures/stp_sample.tsv")


def _table_counts(db_path: Path, table_names: tuple[str, ...]) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in table_names}
    finally:
        conn.close()


def _with_unknown_desk_column(raw_bytes: bytes) -> bytes:
    lines = [line for line in raw_bytes.decode("utf-8-sig").splitlines() if line.strip()]
    header = f"{lines[0]}\tDesk"
    rows = [f"{line}\talpha" for line in lines[1:]]
    return ("\n".join([header, *rows]) + "\n").encode()


def test_import_is_idempotent_and_fills_are_traceable(tmp_path):
    db_path = tmp_path / "trading.db"
    sample = SAMPLE_PATH.read_bytes()

    with TestClient(create_app(db_path)) as client:
        first = client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", sample, "text/plain")})
        first_counts = _table_counts(db_path, ("import_batches", "import_rows", "orders", "fills", "quarantine_rows"))
        second = client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", sample, "text/plain")})
        second_counts = _table_counts(db_path, ("import_batches", "import_rows", "orders", "fills", "quarantine_rows"))

        assert first.status_code == 200
        assert second.status_code == 200
        first_payload = first.json()
        second_payload = second.json()
        assert first_payload["batch_id"] == second_payload["batch_id"]
        assert first_payload["duplicate"] is False
        assert second_payload["duplicate"] is True
        assert first_payload["status"] == "committed"
        assert first_payload["accepted_rows"] == 3
        assert first_payload["quarantined_rows"] == 1
        assert second_counts == first_counts

        fills = client.get("/api/fills?date=2026-06-01").json()["items"]
        assert len(fills) == 2
        assert {fill["execution_id"] for fill in fills} == {"E-100-A", "E-101-A"}
        assert fills[0]["source_batch_id"] == first_payload["batch_id"]
        assert fills[0]["raw_line_number"] == 2
        assert fills[0]["parser_version"].startswith("stp_txt_parser_")
        assert fills[0]["field_mapper_version"].startswith("stp_txt_mapping_")
        assert fills[0]["uses_fallback_idempotency_key"] is False


def test_quarantine_rows_include_reason_and_raw_text(tmp_path):
    sample = SAMPLE_PATH.read_bytes()

    with TestClient(create_app(tmp_path / "trading.db")) as client:
        batch = client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", sample, "text/plain")}).json()
        quarantine = client.get(f"/api/imports/{batch['batch_id']}/quarantine").json()["items"]

        assert len(quarantine) == 1
        assert quarantine[0]["quarantine_id"] == quarantine[0]["id"]
        assert quarantine[0]["reason_code"] == "missing_required_field"
        assert "TSLA" in quarantine[0]["raw_text"]
        assert quarantine[0]["raw_line"] == quarantine[0]["raw_text"]
        assert quarantine[0]["failed_field"] == "price"
        assert quarantine[0]["review_status"] == "open"


def test_empty_file_returns_visible_failure(tmp_path):
    with TestClient(create_app(tmp_path / "trading.db")) as client:
        response = client.post("/api/imports/stp-txt", files={"file": ("empty.tsv", b"", "text/plain")})

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "failed"
        assert payload["status_reason"] == "empty_file"
        assert payload["row_count"] == 0
        assert payload["accepted_rows"] == 0
        assert payload["quarantined_rows"] == 0


def test_daily_summary_uses_committed_fills_only(tmp_path):
    sample = SAMPLE_PATH.read_bytes()

    with TestClient(create_app(tmp_path / "trading.db")) as client:
        client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", sample, "text/plain")})
        summary = client.get("/api/review/daily-summary?date=2026-06-01").json()

        assert summary["source"] == "committed_fills_only"
        assert summary["fill_count"] == 2
        assert summary["traded_quantity"] == 100
        assert summary["quarantine_row_count"] == 1
        assert summary["pnl"] == 150.0
        assert summary["win_rate"] == 1.0
        assert summary["expected_value_per_trade"] == 150.0
        assert summary["net_profit_per_share"] == 1.5
        assert summary["max_single_day_drawdown"] == 0.0


def test_daily_summary_groups_each_flat_round_trip_for_win_rate_and_profit_factor(tmp_path):
    raw = (
        "Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus\n"
        "acct-rt\tAAPL\tBOT\tO-1\tE-1\t100\t10.00\t2026-06-01T09:30:00\tFILLED\n"
        "acct-rt\tAAPL\tSLD\tO-2\tE-2\t100\t11.00\t2026-06-01T09:35:00\tFILLED\n"
        "acct-rt\tAAPL\tBOT\tO-3\tE-3\t100\t12.00\t2026-06-01T10:00:00\tFILLED\n"
        "acct-rt\tAAPL\tSLD\tO-4\tE-4\t100\t11.50\t2026-06-01T10:30:00\tFILLED\n"
        "acct-rt\tMSFT\tSLD\tO-5\tE-5\t50\t20.00\t2026-06-01T11:00:00\tFILLED\n"
        "acct-rt\tMSFT\tBOT\tO-6\tE-6\t50\t18.00\t2026-06-01T11:30:00\tFILLED\n"
    ).encode()

    with TestClient(create_app(tmp_path / "round-trips.db")) as client:
        batch = client.post("/api/imports/stp-txt", files={"file": ("round-trips.tsv", raw, "text/plain")}).json()
        summary = client.get("/api/review/daily-summary?date=2026-06-01").json()

    assert batch["status"] == "committed"
    assert summary["fill_count"] == 6
    assert summary["trade_group_count"] == 3
    assert summary["traded_quantity"] == 250
    assert summary["pnl"] == 150.0
    assert summary["win_rate"] == 0.666667
    assert summary["profit_factor"] == 4.0
    assert summary["expected_value_per_trade"] == 50.0
    assert summary["net_profit_per_share"] == 0.6
    assert summary["max_single_day_drawdown"] == 0.0


def test_batch_detail_and_list_api_contracts_are_stable(tmp_path):
    sample = SAMPLE_PATH.read_bytes()
    expected_hash = hashlib.sha256(sample).hexdigest()
    expected_batch_keys = {
        "id",
        "batch_id",
        "file_name",
        "file_hash",
        "uploaded_at",
        "parser_version",
        "field_mapper_version",
        "status",
        "status_reason",
        "row_count",
        "accepted_rows",
        "quarantined_rows",
        "duplicate",
    }

    with TestClient(create_app(tmp_path / "trading.db")) as client:
        created = client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", sample, "text/plain")}).json()
        detail = client.get(f"/api/imports/{created['batch_id']}").json()
        listed = client.get("/api/imports").json()["items"]

        assert expected_batch_keys <= created.keys()
        assert expected_batch_keys <= detail.keys()
        assert expected_batch_keys <= listed[0].keys()
        assert created["batch_id"] == created["id"]
        assert detail["batch_id"] == created["batch_id"]
        assert listed[0]["batch_id"] == created["batch_id"]
        assert created["file_hash"] == expected_hash
        assert created["file_name"] == "sample.tsv"
        assert detail["duplicate"] is False
        assert listed[0]["duplicate"] is False
        assert isinstance(detail["row_count"], int)
        assert isinstance(detail["accepted_rows"], int)
        assert isinstance(detail["quarantined_rows"], int)


def test_normalized_records_are_idempotent_across_new_batches_with_same_execution_ids(tmp_path):
    db_path = tmp_path / "trading.db"
    sample = SAMPLE_PATH.read_bytes()
    sample_with_unknown_column = _with_unknown_desk_column(sample)

    with TestClient(create_app(db_path)) as client:
        first = client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", sample, "text/plain")}).json()
        second = client.post(
            "/api/imports/stp-txt",
            files={"file": ("sample-with-desk.tsv", sample_with_unknown_column, "text/plain")},
        ).json()
        counts = _table_counts(db_path, ("import_batches", "import_rows", "orders", "fills", "quarantine_rows"))
        fills = client.get("/api/fills?date=2026-06-01").json()["items"]

        assert second["batch_id"] != first["batch_id"]
        assert second["duplicate"] is False
        assert counts == {
            "import_batches": 2,
            "import_rows": 8,
            "orders": 3,
            "fills": 2,
            "quarantine_rows": 2,
        }
        assert {fill["execution_id"] for fill in fills} == {"E-100-A", "E-101-A"}


def test_fallback_fill_key_is_visible_when_execution_id_is_missing(tmp_path):
    raw = (
        "Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus\n"
        " acct-03 \tNVDA\tB\tO-200\t\t5\t100.50\t2026-06-01T13:00:00\tFILLED\n"
    ).encode()
    raw_line_hash = hashlib.sha256(raw.decode().splitlines()[1].encode("utf-8")).hexdigest()

    with TestClient(create_app(tmp_path / "trading.db")) as client:
        batch = client.post("/api/imports/stp-txt", files={"file": ("fallback.tsv", raw, "text/plain")}).json()
        fills = client.get(
            "/api/fills",
            params={"date": "2026-06-01", "account": " acct-03 ", "symbol": "nvda"},
        ).json()["items"]

        assert batch["status"] == "committed"
        assert len(fills) == 1
        fill = fills[0]
        assert fill["fill_id"] == fill["id"]
        assert fill["account_canonical"] == "ACCT-03"
        assert fill["symbol"] == "NVDA"
        assert fill["execution_id"] is None
        assert fill["uses_fallback_idempotency_key"] is True
        assert raw_line_hash in fill["idempotency_key"]


def test_headerless_chinese_fill_txt_imports_and_remains_idempotent(tmp_path):
    db_path = tmp_path / "headerless.db"
    raw = (
        "2026-06-01\t09:31:00\tAAPL\t买入\t100\t10.00\t acct-hk \tDMA\n"
        "2026-06-01\t10:15:00\tAAPL\t卖出\t100\t11.50\tACCT-HK\tDMA\n"
    ).encode()

    with TestClient(create_app(db_path)) as client:
        first = client.post("/api/imports/stp-txt", files={"file": ("headerless.txt", raw, "text/plain")}).json()
        first_counts = _table_counts(db_path, ("import_batches", "import_rows", "orders", "fills", "quarantine_rows"))
        second = client.post("/api/imports/stp-txt", files={"file": ("headerless.txt", raw, "text/plain")}).json()
        second_counts = _table_counts(db_path, ("import_batches", "import_rows", "orders", "fills", "quarantine_rows"))
        fills = client.get("/api/fills?date=2026-06-01").json()["items"]
        summary = client.get("/api/review/daily-summary?date=2026-06-01").json()

    assert first["status"] == "committed"
    assert first["status_reason"] is None
    assert first["row_count"] == 2
    assert first["accepted_rows"] == 2
    assert first["quarantined_rows"] == 0
    assert first["parser_version"] == PARSER_VERSION
    assert first["field_mapper_version"] == FIELD_MAPPER_VERSION
    assert second["batch_id"] == first["batch_id"]
    assert second["duplicate"] is True
    assert second_counts == first_counts
    assert first_counts == {
        "import_batches": 1,
        "import_rows": 2,
        "orders": 2,
        "fills": 2,
        "quarantine_rows": 0,
    }
    assert len(fills) == 2
    assert {fill["side"] for fill in fills} == {"BUY", "SELL"}
    assert all(fill["account_canonical"] == "ACCT-HK" for fill in fills)
    assert all(fill["execution_id"] is None for fill in fills)
    assert all(fill["uses_fallback_idempotency_key"] is True for fill in fills)
    assert summary["source"] == "committed_fills_only"
    assert summary["fill_count"] == 2
    assert summary["traded_quantity"] == 100
    assert summary["quarantine_row_count"] == 0


def test_fallback_fills_preserve_duplicate_raw_rows_in_same_file(tmp_path):
    db_path = tmp_path / "duplicate-rows.db"
    raw = (
        "26/06/01,09:31:00,AAPL,BOT,100,10.00,acct-hk,DMA,12345678,\n"
        "26/06/01,09:31:00,AAPL,BOT,100,10.00,acct-hk,DMA,12345678,\n"
        "26/06/01,10:15:00,AAPL,SLD,200,11.00,acct-hk,DMA,12345679,\n"
    ).encode("utf-16le")

    with TestClient(create_app(db_path)) as client:
        batch = client.post("/api/imports/stp-txt", files={"file": ("dups.txt", raw, "text/plain")}).json()
        fills = client.get("/api/fills?date=2026-06-01").json()["items"]
        summary = client.get("/api/review/daily-summary?date=2026-06-01").json()

    assert batch["status"] == "committed"
    assert batch["accepted_rows"] == 3
    assert len(fills) == 3
    assert summary["fill_count"] == 3
    assert summary["traded_quantity"] == 200
    assert summary["pnl"] == 200.0


def test_fallback_read_model_dedupes_overlapping_changed_hash_batches(tmp_path):
    db_path = tmp_path / "overlapping-fallback.db"
    raw = (
        "26/06/01,09:31:00,AAPL,BOT,100,10.00,acct-hk,DMA,12345678,\n"
        "26/06/01,09:31:00,AAPL,BOT,100,10.00,acct-hk,DMA,12345678,\n"
        "26/06/01,10:15:00,AAPL,SLD,200,11.00,acct-hk,DMA,12345679,\n"
    ).encode("utf-16le")
    same_rows_changed_file_hash = raw + "\n".encode("utf-16le")

    with TestClient(create_app(db_path)) as client:
        first = client.post("/api/imports/stp-txt", files={"file": ("dups.txt", raw, "text/plain")}).json()
        second = client.post(
            "/api/imports/stp-txt",
            files={"file": ("dups-fixed.txt", same_rows_changed_file_hash, "text/plain")},
        ).json()
        counts = _table_counts(db_path, ("import_batches", "import_rows", "orders", "fills", "quarantine_rows"))
        fills = client.get("/api/fills?date=2026-06-01").json()["items"]
        summary = client.get("/api/review/daily-summary?date=2026-06-01").json()

    assert second["batch_id"] != first["batch_id"]
    assert first["accepted_rows"] == 3
    assert second["accepted_rows"] == 3
    assert counts == {
        "import_batches": 2,
        "import_rows": 6,
        "orders": 2,
        "fills": 6,
        "quarantine_rows": 0,
    }
    assert len(fills) == 3
    assert summary["fill_count"] == 3
    assert summary["traded_quantity"] == 200
    assert summary["pnl"] == 200.0


def test_fallback_read_model_dedupes_parser_order_id_shape_drift(tmp_path):
    db_path = tmp_path / "order-id-shape-drift.db"
    raw = "26/06/01,09:31:00,AAPL,BOT,100,10.00,acct-hk,DMA,123456789012,\n".encode("utf-16le")
    conn = connect(db_path)
    try:
        initialize_database(conn)
        conn.executescript(
            """
            INSERT INTO import_batches (
                id, file_name, file_hash, uploaded_at, parser_version, field_mapper_version,
                status, status_reason, row_count, accepted_rows, quarantined_rows
            ) VALUES (
                'batch_old_shape', 'old.txt', 'old-shape-hash', '2026-06-01T09:30:00Z',
                'stp_txt_parser_v0.3.0', 'stp_txt_mapping_v0.3.0',
                'committed', NULL, 1, 1, 0
            );
            INSERT INTO import_rows (
                id, batch_id, raw_line_number, raw_text, raw_line_hash, parser_version,
                field_mapper_version, account_raw, account_canonical, parsed_payload_json,
                row_status, order_id, execution_id, fill_record_id
            ) VALUES (
                'row_old_shape_1', 'batch_old_shape', 1, 'redacted', 'hash_old_shape_1',
                'stp_txt_parser_v0.3.0', 'stp_txt_mapping_v0.3.0',
                'acct-hk', 'ACCT-HK', '{}', 'accepted', '12345678', NULL, 'fill_old_shape_1'
            );
            INSERT INTO orders (
                id, account_raw, account_canonical, symbol, side, order_id, order_status,
                submitted_at, source_batch_id, source_import_row_id, idempotency_key
            ) VALUES (
                'order_old_shape_1', 'acct-hk', 'ACCT-HK', 'AAPL', 'BUY', '12345678', 'FILLED',
                '2026-06-01T09:31:00', 'batch_old_shape', 'row_old_shape_1',
                'ACCT-HK:12345678'
            );
            INSERT INTO fills (
                id, account_raw, account_canonical, symbol, side, order_id, execution_id,
                filled_at, quantity, price, source_batch_id, source_import_row_id, idempotency_key
            ) VALUES (
                'fill_old_shape_1', 'acct-hk', 'ACCT-HK', 'AAPL', 'BUY', '12345678', NULL,
                '2026-06-01T09:31:00', 100, 10, 'batch_old_shape', 'row_old_shape_1',
                'ACCT-HK:fallback:old:12345678:AAPL:BUY:2026-06-01T09:31:00:100:10'
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        new_batch = client.post("/api/imports/stp-txt", files={"file": ("new.txt", raw, "text/plain")}).json()
        counts = _table_counts(db_path, ("import_batches", "import_rows", "orders", "fills", "quarantine_rows"))
        fills = client.get("/api/fills?date=2026-06-01").json()["items"]
        summary = client.get("/api/review/daily-summary?date=2026-06-01").json()

    assert new_batch["status"] == "committed"
    assert counts["import_batches"] == 2
    assert counts["fills"] == 2
    assert len(fills) == 1
    assert fills[0]["order_id"] == "123456789012"
    assert summary["fill_count"] == 1
    assert summary["traded_quantity"] == 0
    assert summary["trade_group_count"] == 0
    assert summary["pnl"] == 0


def test_old_file_level_failed_batch_reparses_after_parser_upgrade(tmp_path):
    db_path = tmp_path / "reparse.db"
    raw = "26/06/01,09:31:00,AAPL,BOT,100,10.00,acct-hk,DMA,12345678,\n".encode("utf-16le")
    file_hash = hashlib.sha256(raw).hexdigest()
    conn = connect(db_path)
    try:
        initialize_database(conn)
        conn.execute(
            """
            INSERT INTO import_batches (
                id, file_name, file_hash, uploaded_at, parser_version, field_mapper_version,
                status, status_reason, row_count, accepted_rows, quarantined_rows
            ) VALUES (
                'batch_old_missing_header', 'headerless.txt', ?, '2026-06-01T09:30:00Z',
                'stp_txt_parser_v0.2.0', 'stp_txt_mapping_v0.2.0',
                'failed', 'missing_header', 0, 0, 0
            )
            """,
            (file_hash,),
        )
        conn.commit()
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        batch = client.post("/api/imports/stp-txt", files={"file": ("headerless.txt", raw, "text/plain")}).json()
        listed = client.get("/api/imports").json()["items"]
        fills = client.get("/api/fills?date=2026-06-01").json()["items"]

    assert batch["batch_id"] == "batch_old_missing_header"
    assert batch["duplicate"] is False
    assert batch["status"] == "committed"
    assert batch["status_reason"] is None
    assert batch["parser_version"] == PARSER_VERSION
    assert batch["field_mapper_version"] == FIELD_MAPPER_VERSION
    assert batch["row_count"] == 1
    assert batch["accepted_rows"] == 1
    assert batch["quarantined_rows"] == 0
    assert len(listed) == 1
    assert len(fills) == 1
    assert fills[0]["order_id"] == "12345678"


def test_old_committed_batch_rebuilds_normalized_rows_after_mapper_upgrade(tmp_path):
    db_path = tmp_path / "committed-rebuild.db"
    raw = (
        "26/06/01,09:31:00,AAPL,BOT,100,10.00,acct-hk,DMA,12345678,\n"
        "26/06/01,09:31:00,AAPL,BOT,100,10.00,acct-hk,DMA,12345678,\n"
        "26/06/01,10:15:00,AAPL,SLD,200,11.00,acct-hk,DMA,12345679,\n"
    ).encode("utf-16le")
    file_hash = hashlib.sha256(raw).hexdigest()
    conn = connect(db_path)
    try:
        initialize_database(conn)
        conn.executescript(
            """
            INSERT INTO import_batches (
                id, file_name, file_hash, uploaded_at, parser_version, field_mapper_version,
                status, status_reason, row_count, accepted_rows, quarantined_rows
            ) VALUES (
                'batch_old_committed', 'dups.txt', 'HASH_PLACEHOLDER', '2026-06-01T09:30:00Z',
                'stp_txt_parser_v0.3.0', 'stp_txt_mapping_v0.3.0',
                'committed', NULL, 3, 3, 0
            );
            INSERT INTO import_rows (
                id, batch_id, raw_line_number, raw_text, raw_line_hash, parser_version,
                field_mapper_version, account_raw, account_canonical, parsed_payload_json,
                row_status, order_id, execution_id, fill_record_id
            ) VALUES (
                'row_old_1', 'batch_old_committed', 1, 'redacted', 'hash_old_1',
                'stp_txt_parser_v0.3.0', 'stp_txt_mapping_v0.3.0',
                'acct-hk', 'ACCT-HK', '{}', 'accepted', '12345678', NULL, 'fill_old_1'
            );
            INSERT INTO fills (
                id, account_raw, account_canonical, symbol, side, order_id, execution_id,
                filled_at, quantity, price, source_batch_id, source_import_row_id, idempotency_key
            ) VALUES (
                'fill_old_1', 'acct-hk', 'ACCT-HK', 'AAPL', 'BUY', '12345678', NULL,
                '2026-06-01T09:31:00', 100, 10, 'batch_old_committed', 'row_old_1',
                'old-fallback-key'
            );
            """
        )
        conn.execute("UPDATE import_batches SET file_hash = ? WHERE id = 'batch_old_committed'", (file_hash,))
        conn.commit()
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        batch = client.post("/api/imports/stp-txt", files={"file": ("dups.txt", raw, "text/plain")}).json()
        fills = client.get("/api/fills?date=2026-06-01").json()["items"]
        summary = client.get("/api/review/daily-summary?date=2026-06-01").json()

    assert batch["batch_id"] == "batch_old_committed"
    assert batch["status"] == "committed"
    assert batch["parser_version"] == PARSER_VERSION
    assert batch["field_mapper_version"] == FIELD_MAPPER_VERSION
    assert batch["accepted_rows"] == 3
    assert len(fills) == 3
    assert summary["fill_count"] == 3
    assert summary["traded_quantity"] == 200
    assert summary["pnl"] == 200.0


def test_file_level_no_data_rows_failure_is_visible(tmp_path):
    header_only = b"Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus\n"

    with TestClient(create_app(tmp_path / "trading.db")) as client:
        response = client.post("/api/imports/stp-txt", files={"file": ("header-only.tsv", header_only, "text/plain")})

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "failed"
        assert payload["status_reason"] == "no_data_rows"
        assert payload["row_count"] == 0


def test_missing_batch_and_invalid_query_return_error_contracts(tmp_path):
    with TestClient(create_app(tmp_path / "trading.db")) as client:
        missing_batch = client.get("/api/imports/batch_missing")
        missing_quarantine = client.get("/api/imports/batch_missing/quarantine")
        invalid_fills_date = client.get("/api/fills?date=20260601")
        invalid_summary_date = client.get("/api/review/daily-summary?date=20260601")
        invalid_summary_group = client.get("/api/review/summary-groups?group_by=account")
        missing_upload_file = client.post("/api/imports/stp-txt")
        empty_summary = client.get("/api/review/summary").json()
        empty_summary_groups = client.get("/api/review/summary-groups?group_by=date").json()["items"]

        assert missing_batch.status_code == 404
        assert missing_batch.json() == {"detail": "batch_not_found"}
        assert missing_quarantine.status_code == 404
        assert missing_quarantine.json() == {"detail": "batch_not_found"}
        assert invalid_fills_date.status_code == 422
        assert invalid_summary_date.status_code == 422
        assert invalid_summary_group.status_code == 422
        assert missing_upload_file.status_code == 422
        assert isinstance(missing_upload_file.json()["detail"], list)
        assert empty_summary["fill_count"] == 0
        assert empty_summary["trade_group_count"] == 0
        assert empty_summary_groups == []

