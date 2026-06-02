from pathlib import Path

from fastapi.testclient import TestClient

from grit_day_trading.api import create_app


def test_import_is_idempotent_and_fills_are_traceable(tmp_path):
    app = create_app(tmp_path / "trading.db")
    client = TestClient(app)
    sample = Path("tests/fixtures/stp_sample.tsv").read_bytes()

    first = client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", sample, "text/plain")})
    second = client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", sample, "text/plain")})

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["batch_id"] == second_payload["batch_id"]
    assert second_payload["duplicate"] is True
    assert first_payload["status"] == "committed"
    assert first_payload["accepted_rows"] == 3
    assert first_payload["quarantined_rows"] == 1

    fills = client.get("/api/fills?date=2026-06-01").json()["items"]
    assert len(fills) == 2
    assert {fill["execution_id"] for fill in fills} == {"E-100-A", "E-101-A"}
    assert fills[0]["source_batch_id"] == first_payload["batch_id"]
    assert fills[0]["raw_line_number"] == 2
    assert fills[0]["parser_version"].startswith("stp_txt_parser_")


def test_quarantine_rows_include_reason_and_raw_text(tmp_path):
    app = create_app(tmp_path / "trading.db")
    client = TestClient(app)
    sample = Path("tests/fixtures/stp_sample.tsv").read_bytes()
    batch = client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", sample, "text/plain")}).json()

    quarantine = client.get(f"/api/imports/{batch['batch_id']}/quarantine").json()["items"]

    assert len(quarantine) == 1
    assert quarantine[0]["reason_code"] == "missing_required_field"
    assert "TSLA" in quarantine[0]["raw_text"]
    assert quarantine[0]["failed_field"] == "price"


def test_empty_file_returns_visible_failure(tmp_path):
    app = create_app(tmp_path / "trading.db")
    client = TestClient(app)

    response = client.post("/api/imports/stp-txt", files={"file": ("empty.tsv", b"", "text/plain")})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["status_reason"] == "empty_file"


def test_daily_summary_uses_committed_fills_only(tmp_path):
    app = create_app(tmp_path / "trading.db")
    client = TestClient(app)
    sample = Path("tests/fixtures/stp_sample.tsv").read_bytes()
    client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", sample, "text/plain")})

    summary = client.get("/api/review/daily-summary?date=2026-06-01").json()

    assert summary["source"] == "committed_fills_only"
    assert summary["fill_count"] == 2
    assert summary["quarantine_row_count"] == 1
    assert summary["pnl"] == 150.0
    assert summary["win_rate"] == 1.0

