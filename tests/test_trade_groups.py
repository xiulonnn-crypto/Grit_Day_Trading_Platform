import json

import pytest
from fastapi.testclient import TestClient

from grit_day_trading.api import create_app
from grit_day_trading.market_archive import archive_market_minutes
from grit_day_trading.market_provider import FakeMarketDataProvider, MarketBar
from grit_day_trading.storage import connect, initialize_database


def test_trade_groups_pair_long_short_partial_close_and_open_positions(tmp_path):
    db_path = tmp_path / "trade-groups.db"
    raw = _trade_group_fixture()

    with TestClient(create_app(db_path)) as client:
        batch = client.post("/api/imports/stp-txt", files={"file": ("groups.tsv", raw, "text/plain")}).json()
        groups = client.get("/api/trade-groups?date=2026-06-01").json()["items"]
        light_groups = client.get("/api/trade-groups?date=2026-06-01&include_details=false").json()["items"]
        repeated = client.get("/api/trade-groups?date=2026-06-01").json()["items"]
        summary = client.get("/api/review/daily-summary?date=2026-06-01").json()

    assert batch["status"] == "committed"
    assert [group["trade_group_id"] for group in groups] == [group["trade_group_id"] for group in repeated]
    assert all(group["trade_group_id"].startswith("tg_") for group in groups)
    serialized = json.dumps(groups)
    assert ":exec:" not in serialized
    assert ":fallback:" not in serialized

    aapl = next(group for group in groups if group["symbol"] == "AAPL")
    msft = next(group for group in groups if group["symbol"] == "MSFT")
    tsla = next(group for group in groups if group["symbol"] == "TSLA")

    assert aapl["status"] == "closed"
    assert aapl["direction"] == "LONG"
    assert aapl["fill_count"] == 4
    assert aapl["total_quantity"] == 150
    assert aapl["avg_entry_price"] == 10.066667
    assert aapl["avg_exit_price"] == 10.64
    assert aapl["pnl"] == 86.0
    assert aapl["holding_minutes"] == 20
    assert aapl["position_drawdown"]["status"] == "insufficient_market_data"
    assert aapl["position_drawdown"]["max_drawdown"] is None
    assert aapl["position_drawdown"]["entry_atr_multiple"] is None
    assert aapl["position_drawdown"]["entry_atr_regime"] == "missing"
    assert aapl["position_drawdown"]["entry_atr_failure_reason"] == "missing_market_data"
    assert aapl["evaluation"]["evaluation_status"] == "insufficient_market_data"
    assert {fill["parser_version"] for fill in aapl["fills"]} == set(aapl["parser_versions"])
    assert {fill["field_mapper_version"] for fill in aapl["fills"]} == set(aapl["field_mapper_versions"])
    light_aapl = next(group for group in light_groups if group["symbol"] == "AAPL")
    assert aapl["details_loaded"] is True
    assert light_aapl["details_loaded"] is False
    assert light_aapl["fills"] == []
    assert light_aapl["evaluation"]["factors"] == []
    assert light_aapl["position_drawdown"]["status"] == aapl["position_drawdown"]["status"]

    assert msft["status"] == "closed"
    assert msft["direction"] == "SHORT"
    assert msft["total_quantity"] == 50
    assert msft["pnl"] == 62.5

    assert tsla["status"] == "open"
    assert tsla["pnl"] is None
    assert tsla["position_drawdown"]["status"] == "not_applicable_open_trade"
    assert tsla["evaluation"]["evaluation_status"] == "not_applicable_open_trade"

    assert summary["trade_group_count"] == 2
    assert summary["traded_quantity"] == 200
    assert summary["pnl"] == 148.5


def test_review_summary_and_drilldown_groups_use_committed_trade_groups(tmp_path):
    db_path = tmp_path / "review-drilldown.db"

    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("groups.tsv", _trade_group_fixture(), "text/plain")})
        overall = client.get("/api/review/summary").json()
        by_symbol = client.get("/api/review/summary-groups?group_by=symbol").json()["items"]
        by_date_for_symbol = client.get("/api/review/summary-groups?group_by=date&symbol=aapl").json()["items"]
        by_symbol_for_date = client.get("/api/review/summary-groups?group_by=symbol&date=2026-06-01").json()["items"]

    assert overall["date"] is None
    assert overall["symbol"] is None
    assert overall["fill_count"] == 8
    assert overall["trade_group_count"] == 2
    assert overall["open_trade_group_count"] == 1
    assert overall["traded_quantity"] == 200
    assert overall["pnl"] == 148.5
    assert overall["expected_value_per_trade"] == 74.25
    assert overall["net_profit_per_share"] == 0.7425
    assert overall["max_single_day_drawdown"] == 0.0

    symbol_groups = {item["group_key"]: item for item in by_symbol}
    assert set(symbol_groups) == {"AAPL", "MSFT", "TSLA"}
    assert symbol_groups["AAPL"]["trade_group_count"] == 1
    assert symbol_groups["AAPL"]["pnl"] == 86.0
    assert symbol_groups["TSLA"]["trade_group_count"] == 0
    assert symbol_groups["TSLA"]["open_trade_group_count"] == 1
    assert symbol_groups["TSLA"]["expected_value_per_trade"] is None
    assert symbol_groups["TSLA"]["net_profit_per_share"] is None
    assert symbol_groups["TSLA"]["max_single_day_drawdown"] == 0.0

    assert [item["group_key"] for item in by_date_for_symbol] == ["2026-06-01"]
    assert by_date_for_symbol[0]["symbol"] == "AAPL"
    assert [item["group_key"] for item in by_symbol_for_date] == ["AAPL", "MSFT", "TSLA"]


def test_trade_groups_can_read_all_dates_for_loss_review_tab(tmp_path):
    db_path = tmp_path / "all-date-loss-groups.db"
    raw = (
        "Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus\n"
        "acct-rt\tAMD\tBOT\tOL-1\tEL-1\t100\t12.00\t2026-06-01T09:30:00\tFILLED\n"
        "acct-rt\tAMD\tSLD\tOL-2\tEL-2\t100\t11.00\t2026-06-01T09:45:00\tFILLED\n"
        "acct-rt\tNVDA\tBOT\tON-1\tEN-1\t10\t100.00\t2026-06-02T09:30:00\tFILLED\n"
        "acct-rt\tNVDA\tSLD\tON-2\tEN-2\t10\t98.00\t2026-06-02T09:45:00\tFILLED\n"
    ).encode()

    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("losses.tsv", raw, "text/plain")})
        groups = client.get("/api/trade-groups?include_details=false").json()["items"]
        invalid_date = client.get("/api/trade-groups?date=20260601")

    losses = [group for group in groups if group["status"] == "closed" and group["pnl"] < 0]
    assert invalid_date.status_code == 422
    assert [group["symbol"] for group in losses] == ["AMD", "NVDA"]
    assert all(group["details_loaded"] is False for group in losses)
    assert all(group["fills"] == [] for group in losses)


def test_trade_group_evaluation_uses_minute_archive_without_mutating_fills(tmp_path):
    db_path = tmp_path / "trade-eval.db"

    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("groups.tsv", _trade_group_fixture(), "text/plain")})

    conn = connect(db_path)
    try:
        initialize_database(conn)
        archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-01",
            source_fill_count=4,
            force=True,
            provider=FakeMarketDataProvider(
                minute_bars={
                    "AAPL": [
                        MarketBar("2026-06-01T09:30:00", 10.0, 10.2, 9.9, 10.1, 1000),
                        MarketBar("2026-06-01T09:35:00", 10.1, 10.35, 10.0, 10.25, 1400),
                        MarketBar("2026-06-01T09:40:00", 10.2, 10.55, 10.15, 10.45, 1800),
                        MarketBar("2026-06-01T09:45:00", 10.45, 10.8, 10.4, 10.7, 2200),
                        MarketBar("2026-06-01T09:50:00", 10.7, 10.9, 10.55, 10.8, 2000),
                    ]
                }
            ),
        )
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        groups = client.get("/api/trade-groups?date=2026-06-01&symbol=AAPL").json()["items"]
        fills = client.get("/api/fills?date=2026-06-01&symbol=AAPL").json()["items"]
        summary = client.get("/api/review/daily-summary?date=2026-06-01&symbol=AAPL").json()

    evaluation = groups[0]["evaluation"]
    drawdown = groups[0]["position_drawdown"]
    assert drawdown["status"] == "available"
    assert drawdown["source"] == "market_minute_archives"
    assert drawdown["source_archive_id"].startswith("minbar_")
    assert len(drawdown["bars_hash"]) == 64
    assert drawdown["bar_count"] == 5
    assert drawdown["price_basis"] == "minute_high_low"
    assert drawdown["entry_atr_period"] == 20
    assert drawdown["entry_atr_multiple"] is None
    assert drawdown["entry_atr_regime"] == "missing"
    assert drawdown["entry_atr_source_archive_id"].startswith("minbar_")
    assert len(drawdown["entry_atr_bars_hash"]) == 64
    assert drawdown["entry_atr_failure_reason"] == "insufficient_atr_history"
    assert drawdown["window_high"] == 10.9
    assert drawdown["window_low"] == 9.9
    assert drawdown["worst_price"] == 9.9
    assert drawdown["max_drawdown_per_share"] == pytest.approx(0.166667)
    assert drawdown["max_drawdown"] == pytest.approx(25.00005)
    assert summary["max_single_day_drawdown"] == pytest.approx(25.00005)
    assert evaluation["model_version"] == "trade_eval_intraday_v1"
    assert evaluation["evaluation_status"] == "available"
    assert evaluation["grade"] in {"A", "B", "C", "D"}
    assert isinstance(evaluation["score"], float)
    assert {factor["name"] for factor in evaluation["factors"]} == {
        "vwap_execution",
        "momentum_alignment",
        "volume_confirmation",
        "mfe_mae",
        "exit_efficiency",
        "pnl_result",
    }
    assert [fill["price"] for fill in fills] == [10.0, 10.2, 10.5, 10.8]


def test_trade_group_entry_atr_multiple_uses_previous_20_minute_bars(tmp_path):
    db_path = tmp_path / "trade-entry-atr.db"
    raw = (
        "Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus\n"
        "acct-rt\tAMD\tBOT\tO-1\tE-1\t100\t100.00\t2026-06-01T09:50:00\tFILLED\n"
        "acct-rt\tAMD\tSLD\tO-2\tE-2\t100\t101.00\t2026-06-01T10:00:00\tFILLED\n"
    ).encode()
    bars = [
        MarketBar(f"2026-06-01T09:{minute:02d}:00", 100.0, 100.5, 99.5, 100.0, 1000)
        for minute in range(30, 50)
    ]
    bars.extend(
        [
            MarketBar("2026-06-01T09:50:00", 100.0, 101.5, 99.5, 101.0, 3000),
            MarketBar("2026-06-01T10:00:00", 101.0, 101.2, 100.8, 101.0, 1800),
        ]
    )

    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("entry-atr.tsv", raw, "text/plain")})

    conn = connect(db_path)
    try:
        initialize_database(conn)
        archive_market_minutes(
            conn,
            symbol="AMD",
            trade_date="2026-06-01",
            source_fill_count=2,
            force=True,
            provider=FakeMarketDataProvider(minute_bars={"AMD": bars}),
        )
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        group = client.get("/api/trade-groups?date=2026-06-01&symbol=AMD").json()["items"][0]

    drawdown = group["position_drawdown"]
    assert drawdown["status"] == "available"
    assert drawdown["entry_atr_period"] == 20
    assert drawdown["entry_atr"] == pytest.approx(1.0)
    assert drawdown["entry_bar_range"] == pytest.approx(2.0)
    assert drawdown["entry_atr_multiple"] == pytest.approx(2.0)
    assert drawdown["entry_atr_regime"] == "high"
    assert drawdown["entry_atr_source_archive_id"].startswith("minbar_")
    assert len(drawdown["entry_atr_bars_hash"]) == 64
    assert drawdown["entry_atr_bar_timestamp"] == "2026-06-01T09:50:00"
    assert drawdown["entry_atr_failure_reason"] is None


def test_short_trade_group_position_drawdown_uses_window_high(tmp_path):
    db_path = tmp_path / "short-drawdown.db"

    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("groups.tsv", _trade_group_fixture(), "text/plain")})

    conn = connect(db_path)
    try:
        initialize_database(conn)
        archive_market_minutes(
            conn,
            symbol="MSFT",
            trade_date="2026-06-01",
            source_fill_count=3,
            force=True,
            provider=FakeMarketDataProvider(
                minute_bars={
                    "MSFT": [
                        MarketBar("2026-06-01T10:00:00", 20.0, 20.1, 19.8, 20.0, 1000),
                        MarketBar("2026-06-01T10:10:00", 19.7, 20.5, 19.4, 19.6, 1200),
                        MarketBar("2026-06-01T10:20:00", 19.0, 19.2, 18.4, 18.5, 1400),
                    ]
                }
            ),
        )
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        group = client.get("/api/trade-groups?date=2026-06-01&symbol=MSFT").json()["items"][0]

    drawdown = group["position_drawdown"]
    assert group["direction"] == "SHORT"
    assert drawdown["status"] == "available"
    assert drawdown["window_high"] == 20.5
    assert drawdown["window_low"] == 18.4
    assert drawdown["worst_price"] == 20.5
    assert drawdown["max_drawdown_per_share"] == 0.5
    assert drawdown["max_drawdown"] == 25.0


def test_trade_group_evaluation_does_not_score_failed_archives(tmp_path):
    db_path = tmp_path / "trade-eval-failed.db"

    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("groups.tsv", _trade_group_fixture(), "text/plain")})

    conn = connect(db_path)
    try:
        initialize_database(conn)
        archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-01",
            source_fill_count=4,
            force=True,
            provider=FakeMarketDataProvider(minute_status={"AAPL": "provider_failed"}),
        )
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        group = client.get("/api/trade-groups?date=2026-06-01&symbol=AAPL").json()["items"][0]

    assert group["evaluation"]["evaluation_status"] == "insufficient_market_data"
    assert group["evaluation"]["score"] is None
    assert group["evaluation"]["grade"] is None
    assert group["evaluation"]["factors"] == []
    assert group["position_drawdown"]["status"] == "insufficient_market_data"
    assert group["position_drawdown"]["max_drawdown"] is None


def test_loss_trade_review_persists_reason_without_mutating_fills(tmp_path):
    db_path = tmp_path / "loss-review.db"

    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("loss.tsv", _losing_trade_group_fixture(), "text/plain")})
        group = client.get("/api/trade-groups?date=2026-06-01").json()["items"][0]
        fills_before = client.get("/api/fills?date=2026-06-01&symbol=AMD").json()["items"]

        review = client.put(
            f"/api/trade-groups/{group['trade_group_id']}/review",
            json={
                "reason_category": "opening_signal",
                "reason_code": "weak_confirmation",
                "note": "入场前没有等二次确认。",
            },
        ).json()
        reviewed_group = client.get("/api/trade-groups?date=2026-06-01").json()["items"][0]
        updated_review = client.put(
            f"/api/trade-groups/{group['trade_group_id']}/review",
            json={
                "reason_category": "closing_signal",
                "reason_code": "stop_too_late",
                "note": "",
            },
        ).json()
        fills_after = client.get("/api/fills?date=2026-06-01&symbol=AMD").json()["items"]

    assert group["status"] == "closed"
    assert group["pnl"] == -100.0
    assert review["source"] == "review_journal"
    assert review["artifact_source"] == "trade_group_read_model"
    assert review["reason_category_label"] == "开仓信号"
    assert review["reason_label"] == "确认不足"
    assert review["parser_versions"] == group["parser_versions"]
    assert reviewed_group["review"]["reason_code"] == "weak_confirmation"
    assert updated_review["id"] == review["id"]
    assert updated_review["reason_category_label"] == "平仓信号"
    assert updated_review["reason_label"] == "止损过慢"
    assert fills_after == fills_before


def test_trade_review_rejects_non_loss_trade_group(tmp_path):
    db_path = tmp_path / "loss-review-rejects-profit.db"

    with TestClient(create_app(db_path)) as client:
        client.post("/api/imports/stp-txt", files={"file": ("groups.tsv", _trade_group_fixture(), "text/plain")})
        profitable = next(
            group for group in client.get("/api/trade-groups?date=2026-06-01").json()["items"] if group["symbol"] == "AAPL"
        )
        response = client.put(
            f"/api/trade-groups/{profitable['trade_group_id']}/review",
            json={"reason_category": "misoperation", "reason_code": "duplicate_order"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "trade_review_requires_loss"


def _trade_group_fixture() -> bytes:
    return (
        "Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus\n"
        "acct-rt\tAAPL\tBOT\tO-1\tE-1\t100\t10.00\t2026-06-01T09:30:00\tFILLED\n"
        "acct-rt\tAAPL\tBOT\tO-2\tE-2\t50\t10.20\t2026-06-01T09:35:00\tFILLED\n"
        "acct-rt\tAAPL\tSLD\tO-3\tE-3\t80\t10.50\t2026-06-01T09:45:00\tFILLED\n"
        "acct-rt\tAAPL\tSLD\tO-4\tE-4\t70\t10.80\t2026-06-01T09:50:00\tFILLED\n"
        "acct-rt\tMSFT\tSLD\tO-5\tE-5\t50\t20.00\t2026-06-01T10:00:00\tFILLED\n"
        "acct-rt\tMSFT\tBOT\tO-6\tE-6\t25\t19.00\t2026-06-01T10:10:00\tFILLED\n"
        "acct-rt\tMSFT\tBOT\tO-7\tE-7\t25\t18.50\t2026-06-01T10:20:00\tFILLED\n"
        "acct-rt\tTSLA\tBOT\tO-8\tE-8\t10\t250.00\t2026-06-01T11:00:00\tFILLED\n"
    ).encode()


def _losing_trade_group_fixture() -> bytes:
    return (
        "Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus\n"
        "acct-rt\tAMD\tBOT\tOL-1\tEL-1\t100\t12.00\t2026-06-01T09:30:00\tFILLED\n"
        "acct-rt\tAMD\tSLD\tOL-2\tEL-2\t100\t11.00\t2026-06-01T09:45:00\tFILLED\n"
    ).encode()
