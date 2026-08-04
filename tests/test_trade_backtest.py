import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from grit_day_trading.api import create_app
from grit_day_trading.market_archive import archive_market_minutes
from grit_day_trading.market_provider import FakeMarketDataProvider, MarketBar
from grit_day_trading.storage import connect, initialize_database


def test_trade_backtest_presets_cap_semantics_persistence_and_idempotency(tmp_path):
    db_path = tmp_path / "trade-backtest-cap.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 800, 10.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "BOT", "A-2", "AE-2", 400, 11.0, "2026-06-01T09:31:00"),
            ("acct-a", "AAPL", "SLD", "A-3", "AE-3", 500, 12.0, "2026-06-01T09:32:00"),
            ("acct-a", "AAPL", "BOT", "A-4", "AE-4", 400, 11.5, "2026-06-01T09:33:00"),
            ("acct-a", "AAPL", "SLD", "A-5", "AE-5", 1100, 12.5, "2026-06-01T09:34:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("cap.tsv", raw, "text/plain")})
    _archive(
        db_path,
        "AAPL",
        [
            _bar("2026-06-01T09:30:00", 10.0),
            _bar("2026-06-01T09:31:00", 11.0),
            _bar("2026-06-01T09:32:00", 12.0),
            _bar("2026-06-01T09:33:00", 11.5),
            _bar("2026-06-01T09:34:00", 12.5),
        ],
        source_fill_count=5,
    )
    before_source_tables = _source_tables_snapshot(db_path)

    with TestClient(create_app(db_path)) as client:
        presets = client.get("/api/review/trade-backtest-presets")
        current_summary = client.get("/api/review/summary").json()
        before_fills = client.get("/api/fills").json()["items"]
        before_groups = client.get("/api/trade-groups").json()["items"]
        first = client.post("/api/review/trade-backtests", json={"start_date": None, "end_date": None})
        second = client.post("/api/review/trade-backtests", json={"start_date": None, "end_date": None})
        listed = client.get("/api/review/trade-backtests?limit=20").json()["items"]
        detail = client.get(f"/api/review/trade-backtests/{first.json()['run_id']}")
        after_fills = client.get("/api/fills").json()["items"]
        after_groups = client.get("/api/trade-groups").json()["items"]
    after_source_tables = _source_tables_snapshot(db_path)

    assert presets.status_code == 200
    assert presets.json()["contract_version"] == "trade_backtest_contract_v5"
    assert presets.json()["rule_catalog_version"] == "trade_backtest_rule_catalog_v5"
    assert presets.json()["engine_version"] == "trade_backtest_engine_v4"
    rule_a_preset = next(item for item in presets.json()["items"] if item["scenario_key"] == "rule_a")
    rule_b_preset = next(item for item in presets.json()["items"] if item["scenario_key"] == "rule_b")
    rule_c_preset = next(item for item in presets.json()["items"] if item["scenario_key"] == "rule_c")
    assert rule_a_preset["preset_version"] == "trade_backtest_rule_a_v5"
    assert rule_a_preset["params"]["max_live_position_quantity"] == 200
    assert rule_b_preset["preset_version"] == "trade_backtest_rule_b_v5"
    assert rule_b_preset["params"]["daily_loss_limit"] == 1000
    assert rule_c_preset["preset_version"] == "trade_backtest_rule_c_v5"
    assert rule_c_preset["params"]["max_live_position_quantity"] == 200
    assert rule_c_preset["params"]["daily_loss_limit"] == 1000
    assert [item["scenario_key"] for item in presets.json()["items"]] == ["baseline", "rule_a", "rule_b", "rule_c"]
    assert first.status_code == 200
    assert first.json()["run_id"] == second.json()["run_id"]
    assert len(listed) == 1
    assert detail.status_code == 200
    scenarios = {item["scenario_key"]: item for item in first.json()["scenarios"]}
    assert scenarios["baseline"]["metrics"]["pnl"] == pytest.approx(2750.0)
    assert scenarios["baseline"]["metrics"]["pnl"] == pytest.approx(current_summary["pnl"])
    assert scenarios["baseline"]["metrics"]["closed_trade_count"] == current_summary["trade_group_count"]
    assert scenarios["baseline"]["metrics"]["traded_quantity"] == current_summary["traded_quantity"]
    assert scenarios["baseline"]["metrics"]["win_rate"] == pytest.approx(current_summary["win_rate"])
    assert scenarios["baseline"]["metrics"]["profit_factor"] == pytest.approx(current_summary["profit_factor"])
    assert scenarios["baseline"]["metrics"]["expected_value_per_trade"] == pytest.approx(
        current_summary["expected_value_per_trade"]
    )
    assert scenarios["baseline"]["metrics"]["net_profit_per_share"] == pytest.approx(
        current_summary["net_profit_per_share"]
    )
    assert scenarios["rule_a"]["metrics"]["pnl"] == pytest.approx(600.0)
    assert scenarios["rule_a"]["metrics"]["capped_open_quantity"] == 1200
    assert scenarios["rule_a"]["metrics"]["traded_quantity"] == 400
    assert scenarios["rule_a"]["metrics"]["delta_vs_baseline"] == pytest.approx(-2150.0)
    assert before_fills == after_fills
    assert before_groups == after_groups
    assert before_source_tables == after_source_tables

    conn = connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM trade_backtest_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM trade_backtest_scenario_results").fetchone()[0] == 4
        stored_run = conn.execute(
            "SELECT source_manifest_json, parser_versions_json, field_mapper_versions_json FROM trade_backtest_runs"
        ).fetchone()
        manifest = json.loads(stored_run["source_manifest_json"])
        assert manifest["source"] == "deduped_committed_fills"
        assert manifest["result_count"] == 4
        assert json.loads(stored_run["parser_versions_json"])
        assert json.loads(stored_run["field_mapper_versions_json"])
        stored_scenarios = conn.execute(
            "SELECT scenario_key, params_json, params_hash, result_hash FROM trade_backtest_scenario_results"
        ).fetchall()
        assert {row["scenario_key"] for row in stored_scenarios} == {"baseline", "rule_a", "rule_b", "rule_c"}
        assert all(len(row["params_hash"]) == 64 and len(row["result_hash"]) == 64 for row in stored_scenarios)
        assert all(isinstance(json.loads(row["params_json"]), dict) for row in stored_scenarios)
    finally:
        conn.close()


def test_trade_backtest_position_cap_applies_to_short_trade_rounds(tmp_path):
    db_path = tmp_path / "trade-backtest-short-cap.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "SLD", "A-1", "AE-1", 1200, 10.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "BOT", "A-2", "AE-2", 1200, 9.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("short-cap.tsv", raw, "text/plain")})
    _archive(
        db_path,
        "AAPL",
        [_bar("2026-06-01T09:30:00", 10.0), _bar("2026-06-01T09:40:00", 9.0)],
        source_fill_count=2,
    )

    with TestClient(create_app(db_path)) as client:
        payload = client.post("/api/review/trade-backtests", json={}).json()

    scenarios = {item["scenario_key"]: item for item in payload["scenarios"]}
    assert scenarios["baseline"]["metrics"]["pnl"] == pytest.approx(1200.0)
    assert scenarios["rule_a"]["metrics"]["pnl"] == pytest.approx(200.0)
    assert scenarios["rule_a"]["metrics"]["capped_open_quantity"] == 1000
    assert scenarios["rule_a"]["metrics"]["traded_quantity"] == 200


def test_trade_backtest_200_share_cap_restores_capacity_after_partial_close(tmp_path):
    db_path = tmp_path / "trade-backtest-cap-restore.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 160, 10.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "BOT", "A-2", "AE-2", 100, 11.0, "2026-06-01T09:31:00"),
            ("acct-a", "AAPL", "SLD", "A-3", "AE-3", 80, 12.0, "2026-06-01T09:32:00"),
            ("acct-a", "AAPL", "BOT", "A-4", "AE-4", 140, 11.5, "2026-06-01T09:33:00"),
            ("acct-a", "AAPL", "SLD", "A-5", "AE-5", 320, 13.0, "2026-06-01T09:34:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("cap-restore.tsv", raw, "text/plain")})
    _archive(
        db_path,
        "AAPL",
        [
            _bar("2026-06-01T09:30:00", 10.0),
            _bar("2026-06-01T09:31:00", 11.0),
            _bar("2026-06-01T09:32:00", 12.0),
            _bar("2026-06-01T09:33:00", 11.5),
            _bar("2026-06-01T09:34:00", 13.0),
        ],
        source_fill_count=5,
    )

    with TestClient(create_app(db_path)) as client:
        payload = client.post("/api/review/trade-backtests", json={}).json()

    rule_a = next(item for item in payload["scenarios"] if item["scenario_key"] == "rule_a")
    assert rule_a["metrics"]["pnl"] == pytest.approx(600.0)
    assert rule_a["metrics"]["capped_open_quantity"] == 120
    assert rule_a["metrics"]["traded_quantity"] == 280


def test_trade_backtest_daily_loss_is_portfolio_wide_forces_exit_and_blocks_new_entries(tmp_path):
    db_path = tmp_path / "trade-backtest-stop.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 100.0, "2026-06-01T09:30:00"),
            ("acct-b", "MSFT", "BOT", "M-1", "ME-1", 100, 100.0, "2026-06-01T09:30:10"),
            ("acct-c", "NVDA", "BOT", "N-1", "NE-1", 100, 50.0, "2026-06-01T09:35:00"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 100, 99.0, "2026-06-01T09:40:00"),
            ("acct-c", "NVDA", "SLD", "N-2", "NE-2", 100, 51.0, "2026-06-01T09:45:00"),
            ("acct-b", "MSFT", "SLD", "M-2", "ME-2", 100, 100.0, "2026-06-01T09:50:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("stop.tsv", raw, "text/plain")})
    _archive(
        db_path,
        "AAPL",
        [
            _bar("2026-06-01T09:30:00", 100.0),
            MarketBar("2026-06-01T09:31:00", 100.0, 100.0, 80.0, 90.0, 1000),
            _bar("2026-06-01T09:40:00", 99.0),
        ],
        source_fill_count=2,
    )
    _archive(
        db_path,
        "MSFT",
        [_bar("2026-06-01T09:30:00", 100.0), _bar("2026-06-01T09:31:00", 100.0), _bar("2026-06-01T09:50:00", 100.0)],
        source_fill_count=2,
    )
    _archive(
        db_path,
        "NVDA",
        [_bar("2026-06-01T09:35:00", 50.0), _bar("2026-06-01T09:45:00", 51.0)],
        source_fill_count=2,
    )

    with TestClient(create_app(db_path)) as client:
        payload = client.post("/api/review/trade-backtests", json={}).json()

    scenarios = {item["scenario_key"]: item for item in payload["scenarios"]}
    rule_b = scenarios["rule_b"]
    assert rule_b["status"] == "completed"
    assert rule_b["metrics"]["pnl"] == pytest.approx(-1000.0)
    assert rule_b["metrics"]["worst_intraday_pnl"] == pytest.approx(-1000.0)
    assert rule_b["metrics"]["forced_exit_count"] == 2
    assert rule_b["metrics"]["stop_trigger_days"] == 1
    assert rule_b["metrics"]["blocked_open_quantity"] == 100
    assert rule_b["metrics"]["blocked_open_trade_count"] == 1
    assert scenarios["rule_c"]["metrics"]["pnl"] == pytest.approx(-1000.0)


def test_trade_backtest_gap_through_daily_limit_exits_at_minute_open(tmp_path):
    db_path = tmp_path / "trade-backtest-gap.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 100.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 100, 95.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("gap.tsv", raw, "text/plain")})
    _archive(
        db_path,
        "AAPL",
        [
            _bar("2026-06-01T09:30:00", 100.0),
            MarketBar("2026-06-01T09:31:00", 70.0, 72.0, 68.0, 71.0, 1000),
            _bar("2026-06-01T09:40:00", 95.0),
        ],
        source_fill_count=2,
    )

    with TestClient(create_app(db_path)) as client:
        payload = client.post("/api/review/trade-backtests", json={}).json()

    rule_b = next(item for item in payload["scenarios"] if item["scenario_key"] == "rule_b")
    assert rule_b["metrics"]["pnl"] == pytest.approx(-3000.0)
    assert rule_b["metrics"]["worst_intraday_pnl"] == pytest.approx(-3000.0)
    assert rule_b["metrics"]["forced_exit_count"] == 1


def test_trade_backtest_short_uses_high_and_defers_fill_minute_market_path(tmp_path):
    db_path = tmp_path / "trade-backtest-short.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "SLD", "A-1", "AE-1", 100, 100.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "BOT", "A-2", "AE-2", 100, 95.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("short.tsv", raw, "text/plain")})
    _archive(
        db_path,
        "AAPL",
        [
            MarketBar("2026-06-01T09:30:00", 100.0, 150.0, 99.0, 100.0, 1000),
            MarketBar("2026-06-01T09:31:00", 100.0, 125.0, 99.0, 100.0, 1000),
            _bar("2026-06-01T09:40:00", 95.0),
        ],
        source_fill_count=2,
    )

    with TestClient(create_app(db_path)) as client:
        payload = client.post("/api/review/trade-backtests", json={}).json()

    rule_b = next(item for item in payload["scenarios"] if item["scenario_key"] == "rule_b")
    assert rule_b["status"] == "completed"
    assert rule_b["metrics"]["pnl"] == pytest.approx(-1000.0)
    assert rule_b["metrics"]["worst_intraday_pnl"] == pytest.approx(-1000.0)
    assert rule_b["metrics"]["forced_exit_count"] == 1


def test_trade_backtest_daily_loss_combines_realized_and_unrealized_pnl(tmp_path):
    db_path = tmp_path / "trade-backtest-realized-unrealized.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 100.0, "2026-06-01T09:30:00"),
            ("acct-b", "MSFT", "BOT", "M-1", "ME-1", 100, 100.0, "2026-06-01T09:30:10"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 100, 90.0, "2026-06-01T09:31:00"),
            ("acct-b", "MSFT", "SLD", "M-2", "ME-2", 100, 100.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("combined.tsv", raw, "text/plain")})
    _archive(
        db_path,
        "AAPL",
        [_bar("2026-06-01T09:30:00", 100.0), _bar("2026-06-01T09:31:00", 90.0)],
        source_fill_count=2,
    )
    _archive(
        db_path,
        "MSFT",
        [
            _bar("2026-06-01T09:30:00", 100.0),
            _bar("2026-06-01T09:31:00", 100.0),
            MarketBar("2026-06-01T09:32:00", 100.0, 100.0, 80.0, 90.0, 1000),
            _bar("2026-06-01T09:40:00", 100.0),
        ],
        source_fill_count=2,
    )

    with TestClient(create_app(db_path)) as client:
        payload = client.post("/api/review/trade-backtests", json={}).json()

    rule_b = next(item for item in payload["scenarios"] if item["scenario_key"] == "rule_b")
    assert rule_b["metrics"]["pnl"] == pytest.approx(-1000.0)
    assert rule_b["metrics"]["closed_trade_count"] == 2
    assert rule_b["metrics"]["forced_exit_count"] == 1


def test_trade_backtest_rule_c_applies_position_cap_before_daily_loss_control(tmp_path):
    db_path = tmp_path / "trade-backtest-rule-c-order.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 2000, 100.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 2000, 99.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("rule-c-order.tsv", raw, "text/plain")})
    _archive(
        db_path,
        "AAPL",
        [
            _bar("2026-06-01T09:30:00", 100.0),
            MarketBar("2026-06-01T09:31:00", 100.0, 100.0, 98.5, 99.5, 1000),
            _bar("2026-06-01T09:40:00", 99.0),
        ],
        source_fill_count=2,
    )

    with TestClient(create_app(db_path)) as client:
        payload = client.post("/api/review/trade-backtests", json={}).json()

    scenarios = {item["scenario_key"]: item for item in payload["scenarios"]}
    assert scenarios["rule_b"]["metrics"]["pnl"] == pytest.approx(-1000.0)
    assert scenarios["rule_b"]["metrics"]["forced_exit_count"] == 1
    assert scenarios["rule_c"]["metrics"]["pnl"] == pytest.approx(-200.0)
    assert scenarios["rule_c"]["metrics"]["capped_open_quantity"] == 1800
    assert scenarios["rule_c"]["metrics"]["forced_exit_count"] == 0


def test_trade_backtest_daily_stop_resets_on_next_trade_date(tmp_path):
    db_path = tmp_path / "trade-backtest-day-reset.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 100.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 100, 99.0, "2026-06-01T09:40:00"),
            ("acct-a", "AAPL", "BOT", "A-3", "AE-3", 100, 100.0, "2026-06-02T09:30:00"),
            ("acct-a", "AAPL", "SLD", "A-4", "AE-4", 100, 99.0, "2026-06-02T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("reset.tsv", raw, "text/plain")})
    for trade_date in ("2026-06-01", "2026-06-02"):
        _archive(
            db_path,
            "AAPL",
            [
                _bar(f"{trade_date}T09:30:00", 100.0),
                MarketBar(f"{trade_date}T09:31:00", 100.0, 100.0, 80.0, 90.0, 1000),
                _bar(f"{trade_date}T09:40:00", 99.0),
            ],
            source_fill_count=2,
            trade_date=trade_date,
        )

    with TestClient(create_app(db_path)) as client:
        payload = client.post("/api/review/trade-backtests", json={}).json()

    rule_b = next(item for item in payload["scenarios"] if item["scenario_key"] == "rule_b")
    assert rule_b["metrics"]["pnl"] == pytest.approx(-2000.0)
    assert rule_b["metrics"]["forced_exit_count"] == 2
    assert rule_b["metrics"]["stop_trigger_days"] == 2


@pytest.mark.parametrize(
    ("rows", "expected_status"),
    [
        (
            [("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 100.0, "2026-06-01T09:30:00")],
            "open_trade_group",
        ),
        (
            [
                ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 100.0, "2026-06-01T09:30:00"),
                ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 100, 101.0, "2026-06-02T09:30:00"),
            ],
            "unsupported_cross_day_position",
        ),
    ],
)
def test_trade_backtest_open_and_cross_day_groups_are_explicitly_unsupported(tmp_path, rows, expected_status):
    db_path = tmp_path / f"trade-backtest-{expected_status}.db"
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("unsupported.tsv", _fixture(rows), "text/plain")})
        payload = client.post("/api/review/trade-backtests", json={}).json()

    assert payload["status"] == "failed"
    assert {item["status"] for item in payload["scenarios"]} == {expected_status}
    assert all(item["metrics"] == {} for item in payload["scenarios"])


def test_trade_backtest_missing_archive_keeps_fill_only_scenarios_and_fails_risk_scenarios(tmp_path):
    db_path = tmp_path / "trade-backtest-missing.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 10.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 100, 11.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("missing.tsv", raw, "text/plain")})
        payload = client.post("/api/review/trade-backtests", json={}).json()

    scenarios = {item["scenario_key"]: item for item in payload["scenarios"]}
    assert payload["status"] == "partial_failed"
    assert scenarios["baseline"]["status"] == "completed"
    assert scenarios["baseline"]["metrics"]["pnl"] == 100
    assert scenarios["baseline"]["metrics"]["worst_intraday_pnl"] is None
    assert scenarios["rule_a"]["status"] == "completed"
    assert scenarios["rule_b"]["status"] == "non_available_archive"
    assert scenarios["rule_c"]["status"] == "non_available_archive"
    assert scenarios["rule_b"]["metrics"] == {}


def test_trade_backtest_rejects_invalid_archive_evidence(tmp_path):
    corruption = "hash"
    expected_status = "invalid_archive"
    db_path = tmp_path / f"trade-backtest-{corruption}.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 10.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 100, 11.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("archive-evidence.tsv", raw, "text/plain")})
    _archive(
        db_path,
        "AAPL",
        [
            _bar("2026-06-01T09:30:00", 10.0),
            _bar("2026-06-01T09:35:00", 10.5),
            _bar("2026-06-01T09:40:00", 11.0),
        ],
        source_fill_count=2,
    )
    conn = connect(db_path)
    try:
        with conn:
            conn.execute("UPDATE market_minute_archives SET bars_hash = 'tampered'")
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        payload = client.post("/api/review/trade-backtests", json={}).json()

    scenarios = {item["scenario_key"]: item for item in payload["scenarios"]}
    assert payload["status"] == "partial_failed"
    assert scenarios["baseline"]["status"] == "completed"
    assert scenarios["rule_a"]["status"] == "completed"
    assert scenarios["rule_b"]["status"] == expected_status
    assert scenarios["rule_c"]["status"] == expected_status
    failed_target = scenarios["rule_b"]["evidence"]["failed_archive_target"]
    assert failed_target["archive_id"].startswith("minbar_")
    assert failed_target["bars_hash"]
    assert failed_target["bar_count"] > 0


def test_trade_backtest_ignores_incomplete_archive_intervals_and_continues_risk_scenarios(tmp_path):
    db_path = tmp_path / "trade-backtest-incomplete-coverage.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 10.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 100, 11.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("archive-gap.tsv", raw, "text/plain")})
    _archive(
        db_path,
        "AAPL",
        [
            _bar("2026-06-01T09:30:00", 10.0),
            _bar("2026-06-01T09:35:00", 10.5),
            _bar("2026-06-01T09:36:00", 10.6),
            _bar("2026-06-01T09:40:00", 11.0),
        ],
        source_fill_count=2,
    )
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT bars_json FROM market_minute_archives").fetchone()
        bars = json.loads(row["bars_json"])[1:-1]
        bars_json = json.dumps(bars, ensure_ascii=False, sort_keys=True)
        bars_hash = hashlib.sha256(bars_json.encode("utf-8")).hexdigest()
        with conn:
            conn.execute(
                """
                UPDATE market_minute_archives
                SET bars_json = ?, bars_hash = ?, bar_count = ?, data_status = 'available', failure_reason = NULL
                """,
                (bars_json, bars_hash, len(bars)),
            )
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        payload = client.post("/api/review/trade-backtests", json={}).json()

    scenarios = {item["scenario_key"]: item for item in payload["scenarios"]}
    assert payload["status"] == "completed"
    for scenario_key in ("rule_b", "rule_c"):
        scenario = scenarios[scenario_key]
        assert scenario["status"] == "completed"
        assert scenario["metrics"]["pnl"] == pytest.approx(100.0)
        assert scenario["metrics"]["worst_intraday_pnl"] is None
        assert scenario["metrics"]["ignored_incomplete_archive_target_count"] == 1
        assert scenario["evidence"]["archive_coverage_complete"] is False
        ignored_target = scenario["evidence"]["ignored_incomplete_archive_targets"][0]
        assert ignored_target["trade_date"] == "2026-06-01"
        assert ignored_target["symbol"] == "AAPL"
        assert ignored_target["coverage_reason"] == "trade_backtest_archive_fill_window_not_covered"


def test_trade_backtest_ignores_localized_partial_archive_without_using_bad_bars(tmp_path):
    db_path = tmp_path / "trade-backtest-localized-partial.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 100.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 100, 101.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("localized-partial.tsv", raw, "text/plain")})
    _archive(
        db_path,
        "AAPL",
        [
            _bar("2026-06-01T09:30:00", 100.0),
            _bar("2026-06-01T09:31:00", 100.0),
            MarketBar("2026-06-01T09:32:00", 100.0, 100.0, 70.0, 100.0, 1000),
            _bar("2026-06-01T09:33:00", 100.0),
            _bar("2026-06-01T09:34:00", 100.0),
            _bar("2026-06-01T09:40:00", 101.0),
        ],
        source_fill_count=2,
    )

    with TestClient(create_app(db_path)) as client:
        payload = client.post("/api/review/trade-backtests", json={}).json()

    scenarios = {item["scenario_key"]: item for item in payload["scenarios"]}
    assert payload["status"] == "completed"
    for scenario_key in ("rule_b", "rule_c"):
        scenario = scenarios[scenario_key]
        assert scenario["status"] == "completed"
        assert scenario["metrics"]["pnl"] == pytest.approx(100.0)
        assert scenario["metrics"]["forced_exit_count"] == 0
        assert scenario["metrics"]["ignored_incomplete_archive_target_count"] == 1
        ignored_target = scenario["evidence"]["ignored_incomplete_archive_targets"][0]
        assert ignored_target["coverage_status"] == "ignored_incomplete"
        assert ignored_target["coverage_reason"] == "isolated_price_discontinuity"
        assert ignored_target["bars_applied"] is False


def test_trade_backtest_archive_hash_change_creates_a_new_run(tmp_path):
    db_path = tmp_path / "trade-backtest-archive-change.db"
    raw = _fixture(
        [
            ("acct-a", "AAPL", "BOT", "A-1", "AE-1", 100, 10.0, "2026-06-01T09:30:00"),
            ("acct-a", "AAPL", "SLD", "A-2", "AE-2", 100, 11.0, "2026-06-01T09:40:00"),
        ]
    )
    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("archive-change.tsv", raw, "text/plain")})
    _archive(
        db_path,
        "AAPL",
        [_bar("2026-06-01T09:30:00", 10.0), _bar("2026-06-01T09:40:00", 11.0)],
        source_fill_count=2,
    )
    with TestClient(create_app(db_path)) as client:
        first = client.post("/api/review/trade-backtests", json={}).json()

    _archive(
        db_path,
        "AAPL",
        [
            _bar("2026-06-01T09:30:00", 10.0),
            _bar("2026-06-01T09:35:00", 10.6),
            _bar("2026-06-01T09:40:00", 11.0),
        ],
        source_fill_count=2,
    )
    with TestClient(create_app(db_path)) as client:
        second = client.post("/api/review/trade-backtests", json={}).json()

    assert first["run_id"] != second["run_id"]
    assert first["archive_scope_hash"] != second["archive_scope_hash"]
    conn = connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM trade_backtest_runs").fetchone()[0] == 2
    finally:
        conn.close()


def test_trade_backtest_rejects_invalid_range_and_missing_run(tmp_path):
    with TestClient(create_app(tmp_path / "trade-backtest-errors.db")) as client:
        invalid = client.post(
            "/api/review/trade-backtests",
            json={"start_date": "2026-06-02", "end_date": "2026-06-01"},
        )
        missing = client.get("/api/review/trade-backtests/not-found")
        health = client.get("/api/healthz").json()

    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "trade_backtest_date_range_invalid"
    assert missing.status_code == 404
    assert missing.json()["detail"] == "trade_backtest_not_found"
    assert health["trade_backtest_contract"] == "trade_backtest_contract_v5"
    assert "/api/review/trade-backtests/{run_id}" in health["required_routes"]


def _fixture(rows):
    lines = ["Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus"]
    lines.extend(
        "\t".join(
            [account, symbol, side, order_id, exec_id, str(quantity), str(price), timestamp, "FILLED"]
        )
        for account, symbol, side, order_id, exec_id, quantity, price, timestamp in rows
    )
    return ("\n".join(lines) + "\n").encode()


def _bar(timestamp, price):
    return MarketBar(timestamp, price, price + 0.05, price - 0.05, price, 1000)


def _archive(db_path, symbol, bars, *, source_fill_count, trade_date="2026-06-01"):
    conn = connect(db_path)
    try:
        initialize_database(conn)
        archive_market_minutes(
            conn,
            symbol=symbol,
            trade_date=trade_date,
            source_fill_count=source_fill_count,
            force=True,
            provider=FakeMarketDataProvider(minute_bars={symbol: bars}),
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
