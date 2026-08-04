import json

import pytest
from fastapi.testclient import TestClient

from grit_day_trading.api import create_app
from grit_day_trading.market_archive import archive_market_minutes
from grit_day_trading.market_provider import FakeMarketDataProvider, MarketBar
from grit_day_trading.storage import connect, initialize_database


def test_trade_backtest_optimization_persists_full_ranked_grid_and_reuses_identical_inputs(tmp_path):
    db_path = tmp_path / "trade-backtest-optimization.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 200, 100.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 200, 110.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        imported = client.post("/api/imports/stp-txt", files={"file": ("optimization.tsv", raw, "text/plain")})
        assert imported.status_code == 200
    _archive(db_path, [_bar("2026-06-01T09:30:00", 100.0), _bar("2026-06-01T09:40:00", 110.0)])
    before = _source_tables_snapshot(db_path)

    request = {
        "start_date": None,
        "end_date": None,
        "max_position_quantities": [100, 50, 100],
        "daily_loss_limits": [1000, 500, 500],
        "objective": "maximize_pnl_v1",
    }
    with TestClient(create_app(db_path)) as client:
        presets = client.get("/api/review/trade-backtest-optimization-presets")
        first = client.post("/api/review/trade-backtest-optimizations", json=request)
        second = client.post("/api/review/trade-backtest-optimizations", json=request)
        listed = client.get("/api/review/trade-backtest-optimizations?limit=20")
        detail = client.get(f"/api/review/trade-backtest-optimizations/{first.json()['run_id']}")
        health = client.get("/api/healthz").json()
    after = _source_tables_snapshot(db_path)

    assert presets.status_code == 200
    assert presets.json()["contract_version"] == "trade_backtest_optimization_contract_v1"
    assert presets.json()["default_max_position_quantities"] == [50, 100, 150, 200, 300, 500, 1000]
    assert presets.json()["default_daily_loss_limits"] == [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]
    assert len(presets.json()["default_max_position_quantities"]) * len(
        presets.json()["default_daily_loss_limits"]
    ) == 70
    assert presets.json()["max_candidate_count"] == 120
    assert presets.json()["bounds"] == {
        "max_position_quantity": {"min": 1, "max": 100000},
        "daily_loss_limit": {"min": 1, "max": 1000000},
    }
    assert first.status_code == 200
    payload = first.json()
    assert payload["run_id"] == second.json()["run_id"]
    assert detail.json()["run_id"] == payload["run_id"]
    assert listed.json()["items"][0]["run_id"] == payload["run_id"]
    assert payload["status"] == "completed"
    assert payload["parameter_space"] == {
        "max_position_quantities": [50, 100],
        "daily_loss_limits": [500, 1000],
    }
    assert payload["total_candidates"] == 4
    assert payload["returned_candidate_count"] == 4
    assert payload["candidate_manifest"]["formula_count"] == 4
    assert payload["candidate_manifest"]["result_count"] == 4
    assert payload["job_id"] == payload["current_batch_id"] == payload["artifact_id"]
    assert payload["source_job_id"] == payload["source_trade_backtest_run_id"]
    assert payload["is_preview"] is False
    assert payload["source_reason"] == "exact_scope_latest_complete_ledger"
    assert payload["best_candidate"]["max_position_quantity"] == 100
    assert payload["best_candidate"]["daily_loss_limit"] == 500
    assert payload["best_candidate"]["metrics"]["pnl"] == pytest.approx(1000.0)
    assert payload["best_candidate"]["rank"] == 1
    assert payload["best_candidate"]["tone"] == "best"
    assert [item["rank"] for item in payload["candidates"]] == [1, 2, 3, 4]
    assert [item["daily_loss_limit"] for item in payload["top_candidates"][:2]] == [500, 1000]
    assert len(payload["matrix"]) == 2
    assert all(len(row["cells"]) == 2 for row in payload["matrix"])
    assert payload["parser_versions"]
    assert payload["field_mapper_versions"]
    assert health["trade_backtest_contract"] == "trade_backtest_contract_v5"
    assert health["trade_backtest_optimization_contract"] == "trade_backtest_optimization_contract_v1"
    assert before == after

    conn = connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM trade_backtest_optimization_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM trade_backtest_optimization_candidates").fetchone()[0] == 4
        stored = conn.execute(
            "SELECT parameter_space_json, source_manifest_json, candidate_manifest_json FROM trade_backtest_optimization_runs"
        ).fetchone()
        assert json.loads(stored["parameter_space_json"]) == payload["parameter_space"]
        assert json.loads(stored["source_manifest_json"])["source_job_id"] == payload["source_job_id"]
        assert json.loads(stored["candidate_manifest_json"])["result_count"] == 4
    finally:
        conn.close()


def test_trade_backtest_optimization_rejects_invalid_grid_and_missing_run(tmp_path):
    db_path = tmp_path / "trade-backtest-optimization-validation.db"
    with TestClient(create_app(db_path)) as client:
        too_many = client.post(
            "/api/review/trade-backtest-optimizations",
            json={
                "max_position_quantities": list(range(1, 12)),
                "daily_loss_limits": list(range(1, 12)),
            },
        )
        fractional_shares = client.post(
            "/api/review/trade-backtest-optimizations",
            json={"max_position_quantities": [10.5], "daily_loss_limits": [500]},
        )
        restored_range = client.post(
            "/api/review/trade-backtest-optimizations",
            json={"max_position_quantities": [1000], "daily_loss_limits": [5000]},
        )
        position_above_safety_limit = client.post(
            "/api/review/trade-backtest-optimizations",
            json={"max_position_quantities": [100001], "daily_loss_limits": [500]},
        )
        loss_above_safety_limit = client.post(
            "/api/review/trade-backtest-optimizations",
            json={"max_position_quantities": [1000], "daily_loss_limits": [1000001]},
        )
        invalid_range = client.post(
            "/api/review/trade-backtest-optimizations",
            json={"start_date": "2026-06-02", "end_date": "2026-06-01"},
        )
        missing = client.get("/api/review/trade-backtest-optimizations/not-found")

    assert too_many.status_code == 422
    assert too_many.json()["detail"] == "trade_backtest_optimization_candidate_cap_exceeded"
    assert fractional_shares.status_code == 422
    assert fractional_shares.json()["detail"] == "trade_backtest_optimization_max_position_quantities_invalid"
    assert restored_range.status_code == 200
    assert position_above_safety_limit.status_code == 422
    assert position_above_safety_limit.json()["detail"] == "trade_backtest_optimization_max_position_quantities_invalid"
    assert loss_above_safety_limit.status_code == 422
    assert loss_above_safety_limit.json()["detail"] == "trade_backtest_optimization_daily_loss_limits_invalid"
    assert invalid_range.status_code == 422
    assert invalid_range.json()["detail"] == "trade_backtest_date_range_invalid"
    assert missing.status_code == 404
    assert missing.json()["detail"] == "trade_backtest_optimization_not_found"


def test_trade_backtest_optimization_fails_without_hard_archive_evidence(tmp_path):
    db_path = tmp_path / "trade-backtest-optimization-missing-archive.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 100.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 100, 99.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("missing-archive.tsv", raw, "text/plain")})
        result = client.post(
            "/api/review/trade-backtest-optimizations",
            json={"max_position_quantities": [50, 100], "daily_loss_limits": [500, 1000]},
        )

    assert result.status_code == 200
    assert result.json()["status"] == "failed"
    assert result.json()["failure_reason"] in {"trade_backtest_missing_archive", "no_bars_returned"}
    assert result.json()["best_candidate"] is None
    assert result.json()["returned_candidate_count"] == 0
    assert result.json()["candidate_manifest"]["formula_count"] == 4
    assert result.json()["candidate_manifest"]["result_count"] == 0


def test_trade_backtest_optimization_ignores_incomplete_archive_window_and_continues(tmp_path):
    db_path = tmp_path / "trade-backtest-optimization-incomplete-archive.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 100.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 100, 101.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("incomplete.tsv", raw, "text/plain")})
    _archive(db_path, [_bar("2026-06-01T09:30:00", 100.0)])

    with TestClient(create_app(db_path)) as client:
        result = client.post(
            "/api/review/trade-backtest-optimizations",
            json={"max_position_quantities": [100], "daily_loss_limits": [500]},
        )

    assert result.status_code == 200
    assert result.json()["status"] == "completed"
    assert result.json()["best_candidate"]["metrics"]["pnl"] == pytest.approx(100.0)
    assert result.json()["best_candidate"]["metrics"]["ignored_incomplete_archive_target_count"] == 1


def _fixture(rows):
    lines = ["Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus"]
    lines.extend(
        "\t".join([account, symbol, side, order_id, exec_id, str(quantity), str(price), timestamp, "FILLED"])
        for account, symbol, side, order_id, exec_id, quantity, price, timestamp in rows
    )
    return ("\n".join(lines) + "\n").encode()


def _bar(timestamp, price):
    return MarketBar(timestamp, price, price + 0.05, price - 0.05, price, 1000)


def _archive(db_path, bars):
    conn = connect(db_path)
    try:
        initialize_database(conn)
        archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-01",
            source_fill_count=2,
            force=True,
            provider=FakeMarketDataProvider(minute_bars={"AAPL": bars}),
        )
    finally:
        conn.close()


def _source_tables_snapshot(db_path):
    conn = connect(db_path)
    try:
        return {
            table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()]
            for table in ("orders", "fills", "trade_reviews", "strategy_configs", "market_minute_archives")
        }
    finally:
        conn.close()
