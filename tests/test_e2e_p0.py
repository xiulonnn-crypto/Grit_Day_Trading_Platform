import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from grit_day_trading.api import create_app
from grit_day_trading.parser import FIELD_MAPPER_VERSION, PARSER_VERSION, parse_stp_txt


REFERENCE_FIXTURE = Path("tests/fixtures/stp_sample.tsv")
EDGE_FIXTURE = Path("tests/fixtures/stp_p0_edge_cases.tsv")
MISSING_REQUIRED_FIXTURE = Path("tests/fixtures/stp_missing_required.tsv")


def test_reference_and_simulated_fixtures_cover_p0_parser_matrix():
    reference = parse_stp_txt(REFERENCE_FIXTURE.read_bytes())
    edge = parse_stp_txt(EDGE_FIXTURE.read_bytes())

    assert reference.file_error is None
    assert edge.file_error is None
    assert reference.parser_version == edge.parser_version == PARSER_VERSION
    assert reference.field_mapper_version == edge.field_mapper_version == FIELD_MAPPER_VERSION

    reference_rows = _rows_by_order_id(reference)
    edge_rows = _rows_by_order_id(edge)

    assert reference_rows["O-100"].normalized["account_raw"] == "acct-01"
    assert reference_rows["O-100"].normalized["account_canonical"] == "ACCT-01"
    assert reference_rows["O-102"].normalized["has_fill"] is False

    assert edge_rows["O-P0-001"].normalized["account_canonical"] == "ACCT-QA"
    assert edge_rows["O-P0-002"].normalized["status"] == "PARTIAL"
    assert edge_rows["O-P0-003"].normalized["execution_id"] == ""
    assert edge_rows["O-P0-004"].normalized["has_fill"] is False
    assert edge_rows["O-P0-005"].normalized["timestamp"].startswith("2026-06-02")
    assert edge_rows["O-P0-001"].parsed_payload["_unknown_columns"] == ["DeskNote"]

    edge_quarantine = [row for row in edge.rows if row.row_status == "quarantine"]
    assert len(edge_quarantine) == 1
    assert edge_quarantine[0].failed_field == "price"
    assert edge_quarantine[0].reason_code == "missing_required_field"


def test_p0_import_evidence_is_consistent_across_db_api_and_ui_read_model(tmp_path):
    db_path = tmp_path / "p0.db"
    app = create_app(db_path)
    sample = EDGE_FIXTURE.read_bytes()

    with TestClient(app) as client:
        first = client.post("/api/imports/stp-txt", files={"file": ("edge.tsv", sample, "text/plain")})
        second = client.post("/api/imports/stp-txt", files={"file": ("edge.tsv", sample, "text/plain")})

        assert first.status_code == 200
        assert second.status_code == 200
        first_payload = first.json()
        second_payload = second.json()

        assert first_payload["batch_id"] == second_payload["batch_id"]
        assert second_payload["duplicate"] is True
        assert first_payload["status"] == "committed"
        assert first_payload["accepted_rows"] == 5
        assert first_payload["quarantined_rows"] == 1
        assert first_payload["parser_version"] == PARSER_VERSION
        assert first_payload["field_mapper_version"] == FIELD_MAPPER_VERSION

        fills_day_1 = client.get("/api/fills?date=2026-06-01").json()["items"]
        fills_day_2 = client.get("/api/fills?date=2026-06-02").json()["items"]
        quarantine = client.get(f"/api/imports/{first_payload['batch_id']}/quarantine").json()["items"]
        summary_day_1 = client.get("/api/review/daily-summary?date=2026-06-01").json()
        summary_day_2 = client.get("/api/review/daily-summary?date=2026-06-02").json()

    db = _db_snapshot(db_path, first_payload["batch_id"])

    assert db["batch"]["file_hash"] == first_payload["file_hash"]
    assert len(db["file_hash"]) == 64
    assert db["counts"] == {
        "import_batches": 1,
        "import_rows": 6,
        "orders": 5,
        "fills": 4,
        "quarantine_rows": 1,
    }
    assert db["accepted_import_rows"] == first_payload["accepted_rows"]
    assert db["quarantined_import_rows"] == first_payload["quarantined_rows"]
    assert len(db["raw_line_hashes"]) == 6
    assert all(raw_text for raw_text in db["raw_texts"])
    assert all(version == PARSER_VERSION for version in db["parser_versions"])
    assert all(version == FIELD_MAPPER_VERSION for version in db["field_mapper_versions"])
    assert db["accounts"]["acct-qa"] == "ACCT-QA"
    assert db["unknown_columns"] == ["DeskNote"]

    assert len(fills_day_1) == 3
    assert len(fills_day_2) == 1
    assert {fill["execution_id"] for fill in fills_day_1} == {"E-P0-001-A", "E-P0-002-A", None}
    assert any(fill["execution_id"] is None for fill in fills_day_1)
    assert all(fill["source_batch_id"] == first_payload["batch_id"] for fill in fills_day_1 + fills_day_2)
    assert all(fill["parser_version"] == PARSER_VERSION for fill in fills_day_1 + fills_day_2)
    assert all(fill["field_mapper_version"] == FIELD_MAPPER_VERSION for fill in fills_day_1 + fills_day_2)

    assert len(quarantine) == db["counts"]["quarantine_rows"]
    assert quarantine[0]["failed_field"] == "price"
    assert quarantine[0]["reason_code"] == "missing_required_field"
    assert quarantine[0]["review_status"] == "open"

    assert summary_day_1["source"] == "committed_fills_only"
    assert summary_day_1["fill_count"] == len(fills_day_1)
    assert summary_day_1["quarantine_row_count"] == len(quarantine)
    assert summary_day_1["pnl"] == 15.0
    assert summary_day_1["win_rate"] == 1.0
    assert summary_day_1["profit_factor"] is None

    assert summary_day_2["source"] == "committed_fills_only"
    assert summary_day_2["fill_count"] == len(fills_day_2)
    assert summary_day_2["pnl"] == -400.0

    ui_batch = _ui_batch_card(first_payload)
    ui_fills = [_ui_fill_row(fill) for fill in fills_day_1]
    ui_quarantine = [_ui_quarantine_card(row) for row in quarantine]
    ui_summary = _ui_summary_cards(summary_day_1)

    assert ui_batch == {
        "status": "committed",
        "accepted": 5,
        "quarantine": 1,
        "trace_batch_id": first_payload["batch_id"],
    }
    assert any(row["exec_display"] == "fallback" for row in ui_fills)
    assert all(row["trace"].startswith("line ") and PARSER_VERSION in row["trace"] for row in ui_fills)
    assert ui_quarantine == [{"line": 7, "reason_code": "missing_required_field", "failed_field": "price"}]
    assert ui_summary == {
        "成交数": 3,
        "PnL": 15.0,
        "胜率": "100%",
        "盈亏比": "N/A",
        "异常行": 1,
    }


def test_negative_import_paths_leave_visible_status_without_committed_fills(tmp_path):
    db_path = tmp_path / "negative.db"
    app = create_app(db_path)

    with TestClient(app) as client:
        empty = client.post("/api/imports/stp-txt", files={"file": ("empty.tsv", b"", "text/plain")}).json()
        missing = client.post(
            "/api/imports/stp-txt",
            files={"file": ("missing.tsv", MISSING_REQUIRED_FIXTURE.read_bytes(), "text/plain")},
        ).json()

        empty_quarantine = client.get(f"/api/imports/{empty['batch_id']}/quarantine").json()["items"]
        missing_quarantine = client.get(f"/api/imports/{missing['batch_id']}/quarantine").json()["items"]
        fills = client.get("/api/fills?date=2026-06-01").json()["items"]
        summary = client.get("/api/review/daily-summary?date=2026-06-01").json()

    assert empty["status"] == "failed"
    assert empty["status_reason"] == "empty_file"
    assert empty["accepted_rows"] == 0
    assert empty["quarantined_rows"] == 0
    assert empty_quarantine == []

    assert missing["status"] == "failed"
    assert missing["status_reason"] == "no_valid_rows"
    assert missing["accepted_rows"] == 0
    assert missing["quarantined_rows"] == 2
    assert {row["failed_field"] for row in missing_quarantine} == {"order_id", "symbol"}
    assert all(row["reason_code"] == "missing_required_field" for row in missing_quarantine)

    assert fills == []
    assert summary["source"] == "committed_fills_only"
    assert summary["fill_count"] == 0
    assert summary["pnl"] == 0
    assert summary["win_rate"] == 0
    assert summary["quarantine_row_count"] == 0

    db = _db_snapshot(db_path, missing["batch_id"])
    assert db["counts"]["fills"] == 0
    assert db["counts"]["orders"] == 0
    assert db["counts"]["quarantine_rows"] == 2


def test_ui_import_list_read_model_exposes_batch_id_for_batch_selection(tmp_path):
    db_path = tmp_path / "ui-list.db"
    app = create_app(db_path)

    with TestClient(app) as client:
        batch = client.post(
            "/api/imports/stp-txt",
            files={"file": ("edge.tsv", EDGE_FIXTURE.read_bytes(), "text/plain")},
        ).json()
        listed = client.get("/api/imports").json()["items"][0]

    assert listed["batch_id"] == batch["batch_id"]


def _rows_by_order_id(parse_result):
    rows = {}
    for row in parse_result.rows:
        payload = row.parsed_payload
        order_id = payload.get("OrderID")
        if order_id:
            rows[order_id] = row
    return rows


def _db_snapshot(db_path: Path, batch_id: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("import_batches", "import_rows", "orders", "fills", "quarantine_rows")
        }
        batch = dict(conn.execute("SELECT * FROM import_batches WHERE id = ?", (batch_id,)).fetchone())
        import_rows = conn.execute(
            """
            SELECT raw_text, raw_line_hash, parser_version, field_mapper_version,
                   account_raw, account_canonical, parsed_payload_json, row_status
            FROM import_rows
            WHERE batch_id = ?
            ORDER BY raw_line_number
            """,
            (batch_id,),
        ).fetchall()
        payloads = [json.loads(row["parsed_payload_json"]) for row in import_rows]
        accounts = {
            row["account_raw"].strip().lower(): row["account_canonical"]
            for row in import_rows
            if row["account_raw"]
        }
        return {
            "batch": batch,
            "file_hash": batch["file_hash"],
            "counts": counts,
            "accepted_import_rows": sum(1 for row in import_rows if row["row_status"] == "accepted"),
            "quarantined_import_rows": sum(1 for row in import_rows if row["row_status"] == "quarantine"),
            "raw_texts": [row["raw_text"] for row in import_rows],
            "raw_line_hashes": {row["raw_line_hash"] for row in import_rows},
            "parser_versions": {row["parser_version"] for row in import_rows},
            "field_mapper_versions": {row["field_mapper_version"] for row in import_rows},
            "accounts": accounts,
            "unknown_columns": payloads[0]["_unknown_columns"],
        }
    finally:
        conn.close()


def _ui_batch_card(batch):
    return {
        "status": batch["status"],
        "accepted": batch["accepted_rows"],
        "quarantine": batch["quarantined_rows"],
        "trace_batch_id": batch["batch_id"],
    }


def _ui_fill_row(fill):
    return {
        "time": fill["filled_at"],
        "account": fill["account_canonical"],
        "symbol": fill["symbol"],
        "side": fill["side"],
        "quantity": fill["quantity"],
        "price": fill["price"],
        "exec_display": fill["execution_id"] or "fallback",
        "trace": f"line {fill['raw_line_number']} · {fill['parser_version']}",
    }


def _ui_quarantine_card(row):
    return {
        "line": row["raw_line_number"],
        "reason_code": row["reason_code"],
        "failed_field": row["failed_field"],
    }


def _ui_summary_cards(summary):
    return {
        "成交数": summary["fill_count"],
        "PnL": summary["pnl"],
        "胜率": f"{round(summary['win_rate'] * 100)}%",
        "盈亏比": summary["profit_factor"] if summary["profit_factor"] is not None else "N/A",
        "异常行": summary["quarantine_row_count"],
    }
