import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from grit_day_trading.api import create_app


SAMPLE_PATH = Path("tests/fixtures/stp_sample.tsv")


def test_p1_market_context_and_watchlist_are_consistent_across_db_api_and_ui_read_model(tmp_path):
    db_path = tmp_path / "p1-e2e.db"

    with TestClient(create_app(db_path)) as client:
        batch = client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", SAMPLE_PATH.read_bytes(), "text/plain")}).json()
        fill = client.get("/api/fills?date=2026-06-01").json()["items"][0]
        replay = client.post(
            "/api/market-context/replay",
            json={"fill_id": fill["fill_id"], "provider": "fake", "minutes_before": 1, "minutes_after": 1},
        ).json()
        fill_context = client.get(f"/api/fills/{fill['fill_id']}/market-context").json()
        watchlist = client.post("/api/watchlist/generate", json={"date": "2026-06-01", "provider": "fake"}).json()
        listed_watchlist = client.get("/api/watchlist?date=2026-06-01").json()

    db = _db_snapshot(db_path)
    ui_context = _ui_market_context(replay)
    ui_watchlist = [_ui_watchlist_item(item) for item in watchlist["items"]]

    assert batch["status"] == "committed"
    assert replay["snapshot_id"] == fill_context["snapshot_id"]
    assert replay["fill_id"] == fill["fill_id"]
    assert replay["provider"] == "fake"
    assert replay["data_status"] == "available"
    assert replay["bars_hash"] == db["market_context"]["bars_hash"]
    assert replay["requested_start"] == db["market_context"]["requested_start"]
    assert replay["requested_end"] == db["market_context"]["requested_end"]
    assert replay["vwap"] == db["market_context"]["vwap"]

    assert listed_watchlist["run_id"] == watchlist["run_id"]
    assert watchlist["item_count"] == len(watchlist["items"])
    assert db["watchlist_run"]["item_count"] == watchlist["item_count"]
    assert {item["symbol"] for item in watchlist["items"]} == {item["symbol"] for item in db["watchlist_items"]}
    assert all(item["reason_codes"] for item in watchlist["items"])
    assert all(item["metrics"] for item in watchlist["items"])

    assert ui_context == {
        "fill_id": fill["fill_id"],
        "status": "available",
        "vwap": replay["vwap"],
        "hash": replay["bars_hash"],
    }
    assert all(item["reason_count"] >= 1 and item["has_metrics"] for item in ui_watchlist)


def _db_snapshot(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return {
            "market_context": dict(conn.execute("SELECT * FROM market_context_snapshots").fetchone()),
            "watchlist_run": dict(conn.execute("SELECT * FROM watchlist_runs").fetchone()),
            "watchlist_items": [dict(row) for row in conn.execute("SELECT * FROM watchlist_items").fetchall()],
        }
    finally:
        conn.close()


def _ui_market_context(snapshot):
    return {
        "fill_id": snapshot["fill_id"],
        "status": snapshot["data_status"],
        "vwap": snapshot["vwap"],
        "hash": snapshot["bars_hash"],
    }


def _ui_watchlist_item(item):
    return {
        "symbol": item["symbol"],
        "rank": item["rank"],
        "reason_count": len(item["reason_codes"]),
        "has_metrics": bool(item["metrics"]),
    }
