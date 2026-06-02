import hashlib
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from grit_day_trading.api import create_app


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
        assert summary["quarantine_row_count"] == 1
        assert summary["pnl"] == 150.0
        assert summary["win_rate"] == 1.0


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
        missing_upload_file = client.post("/api/imports/stp-txt")

        assert missing_batch.status_code == 404
        assert missing_batch.json() == {"detail": "batch_not_found"}
        assert missing_quarantine.status_code == 404
        assert missing_quarantine.json() == {"detail": "batch_not_found"}
        assert invalid_fills_date.status_code == 422
        assert invalid_summary_date.status_code == 422
        assert missing_upload_file.status_code == 422
        assert isinstance(missing_upload_file.json()["detail"], list)

