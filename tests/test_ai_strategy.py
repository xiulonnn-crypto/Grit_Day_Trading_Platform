import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from grit_day_trading.ai_strategy import (
    AI_STRATEGY_CATALOG_VERSION,
    AI_STRATEGY_RANKING_VERSION,
)
from grit_day_trading.api import create_app
from grit_day_trading.storage import connect, initialize_database
from grit_day_trading.strategy import list_strategy_configs, update_strategy_config


RESEARCH_ORDER = [
    "five_minute_opening_range_breakout_v1",
    "vwap_opening_drive_v1",
    "last_hour_intraday_momentum_v1",
    "fifteen_minute_opening_range_retest_v1",
    "vwap_trend_pullback_v1",
]


def test_ai_strategy_recommendations_default_to_research_order_without_fabricated_metrics(tmp_path: Path):
    client = TestClient(create_app(tmp_path / "ai-strategy.db"))

    first = client.get(
        "/api/ai-strategy-recommendations",
        params={"end_date": "2026-07-13", "symbols": "mu, nvda, MU"},
    )
    second = client.get(
        "/api/ai-strategy-recommendations",
        params={"end_date": "2026-07-13", "symbols": "NVDA,MU"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    payload = first.json()
    assert payload["catalog_version"] == AI_STRATEGY_CATALOG_VERSION
    assert payload["ranking_version"] == AI_STRATEGY_RANKING_VERSION
    assert payload["ranking_basis"] == "research_prior"
    assert payload["evidence_status"] == "insufficient"
    assert payload["symbols"] == ["MU", "NVDA"]
    assert payload["initial_capital"] == 100000.0
    assert payload["entry_capital_ratio"] == 0.2
    assert payload["position_notional"] == 20000.0
    assert payload["recommendation_key"] == second.json()["recommendation_key"]
    assert [item["template_key"] for item in payload["items"]] == RESEARCH_ORDER
    assert [item["rank"] for item in payload["items"]] == [1, 2, 3, 4, 5]
    assert all(item["expectation"]["status"] == "research_only" for item in payload["items"])
    assert all(item["expectation"]["expected_pnl_per_closed_trade"] is None for item in payload["items"])
    assert all(item["expectation"]["total_pnl"] is None for item in payload["items"])
    assert all(item["capital"]["concurrency_modeled"] is False for item in payload["items"])
    assert all(item["deep_link"]["workspace"] == "strategy" for item in payload["items"])
    assert payload["retired_catalog_template_keys"] == [
        "one_minute_trend_rider_v1",
        "bb_squeeze_breakout_v1",
        "momentum_mean_reversion_v1",
        "institutional_liquidity_sweep_v1",
        "one_minute_range_fader_v1",
    ]
    assert "day_results" not in json.dumps(payload, ensure_ascii=False)


def test_ai_strategy_recommendations_use_local_expectancy_only_when_all_five_are_comparable(tmp_path: Path):
    db_path = tmp_path / "ai-strategy-local.db"
    client = TestClient(create_app(db_path))
    catalog = client.get(
        "/api/ai-strategy-recommendations",
        params={"end_date": "2026-07-13", "symbols": "MU"},
    ).json()
    pnl_by_template = {
        "five_minute_opening_range_breakout_v1": (100.0, 1.1),
        "vwap_opening_drive_v1": (500.0, 1.5),
        "last_hour_intraday_momentum_v1": (300.0, 1.4),
        "fifteen_minute_opening_range_retest_v1": (200.0, 1.3),
        "vwap_trend_pullback_v1": (500.0, 2.0),
    }

    conn = connect(db_path)
    initialize_database(conn)
    try:
        configs = {config["strategy_id"]: config for config in list_strategy_configs(conn)}
        for item in catalog["items"]:
            config = configs[item["strategy_id"]]
            total_pnl, profit_factor = pnl_by_template[item["template_key"]]
            _insert_test_batch(
                conn,
                batch_id=f"batch_{item['template_key']}",
                strategy_id=item["strategy_id"],
                params_json=json.dumps(item["recommended_params"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                params_hash=item["recommended_params_hash"],
                template_version=config["template_version"],
                total_pnl=total_pnl,
                profit_factor=profit_factor,
            )
    finally:
        conn.close()

    response = client.get(
        "/api/ai-strategy-recommendations",
        params={"end_date": "2026-07-13", "symbols": "MU"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ranking_basis"] == "local_backtest"
    assert payload["evidence_status"] == "verified"
    assert [item["template_key"] for item in payload["items"]] == [
        "vwap_trend_pullback_v1",
        "vwap_opening_drive_v1",
        "last_hour_intraday_momentum_v1",
        "fifteen_minute_opening_range_retest_v1",
        "five_minute_opening_range_breakout_v1",
    ]
    assert all(item["expectation"]["status"] == "backtested" for item in payload["items"])
    assert payload["items"][0]["expectation"]["expected_pnl_per_closed_trade"] == pytest.approx(50.0)
    assert payload["items"][0]["expectation"]["profit_factor"] == pytest.approx(2.0)
    assert payload["items"][0]["expectation"]["closed_group_count"] == 10
    assert len(payload["items"][0]["expectation"]["matching_batch_ids"]) == 1
    assert "day_results" not in json.dumps(payload, ensure_ascii=False)


def test_ai_strategy_recommendations_fall_back_when_current_params_are_stale(tmp_path: Path):
    db_path = tmp_path / "ai-strategy-stale.db"
    client = TestClient(create_app(db_path))
    catalog = client.get(
        "/api/ai-strategy-recommendations",
        params={"end_date": "2026-07-13", "symbols": "MU"},
    ).json()

    conn = connect(db_path)
    initialize_database(conn)
    try:
        configs = {config["strategy_id"]: config for config in list_strategy_configs(conn)}
        for item in catalog["items"]:
            config = configs[item["strategy_id"]]
            _insert_test_batch(
                conn,
                batch_id=f"batch_{item['template_key']}",
                strategy_id=item["strategy_id"],
                params_json=json.dumps(item["recommended_params"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                params_hash=item["recommended_params_hash"],
                template_version=config["template_version"],
                total_pnl=250.0,
                profit_factor=1.5,
            )
        trend_item = next(item for item in catalog["items"] if item["template_key"] == "five_minute_opening_range_breakout_v1")
        current_params = dict(trend_item["recommended_params"])
        current_params["min_relative_volume"] = 1.0
        update_strategy_config(conn, trend_item["strategy_id"], params=current_params)
    finally:
        conn.close()

    payload = client.get(
        "/api/ai-strategy-recommendations",
        params={"end_date": "2026-07-13", "symbols": "MU"},
    ).json()

    assert payload["ranking_basis"] == "research_prior"
    assert payload["evidence_status"] == "partial"
    assert [item["template_key"] for item in payload["items"]] == RESEARCH_ORDER
    trend = payload["items"][0]
    assert trend["expectation"]["status"] == "partial"
    assert trend["current_config_alignment"]["matches_recommended_params"] is False
    assert "current_config_differs_from_recommended" in trend["expectation"]["failure_reasons"]


@pytest.mark.parametrize(
    ("issue", "expected_reason"),
    [
        ("insufficient_closed_groups", "closed_groups_below_10"),
        ("insufficient_bars", "insufficient_minute_bars"),
        ("null_profit_factor", "profit_factor_unavailable"),
        ("strategy_test_failed", "engine_failed"),
    ],
)
def test_ai_strategy_recommendations_keep_research_order_when_any_evidence_is_not_comparable(
    tmp_path: Path,
    issue: str,
    expected_reason: str,
):
    db_path = tmp_path / f"ai-strategy-{issue}.db"
    client = TestClient(create_app(db_path))
    catalog = client.get(
        "/api/ai-strategy-recommendations",
        params={"end_date": "2026-07-13", "symbols": "MU"},
    ).json()

    conn = connect(db_path)
    initialize_database(conn)
    affected_template = "five_minute_opening_range_breakout_v1"
    affected_batch_id = f"batch_{affected_template}"
    try:
        configs = {config["strategy_id"]: config for config in list_strategy_configs(conn)}
        for item in catalog["items"]:
            _insert_test_batch(
                conn,
                batch_id=f"batch_{item['template_key']}",
                strategy_id=item["strategy_id"],
                params_json=json.dumps(item["recommended_params"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                params_hash=item["recommended_params_hash"],
                template_version=configs[item["strategy_id"]]["template_version"],
                total_pnl=250.0,
                profit_factor=1.5,
            )
        with conn:
            if issue == "insufficient_closed_groups":
                conn.execute(
                    "UPDATE strategy_test_day_results SET closed_group_count = 0 WHERE batch_id = ?",
                    (affected_batch_id,),
                )
            elif issue == "insufficient_bars":
                conn.execute(
                    "UPDATE strategy_test_day_results SET status = 'insufficient_bars', failure_reason = 'insufficient_minute_bars' WHERE batch_id = ? AND trade_date = '2026-07-01'",
                    (affected_batch_id,),
                )
            elif issue == "null_profit_factor":
                conn.execute(
                    "UPDATE strategy_test_batches SET profit_factor = NULL WHERE id = ?",
                    (affected_batch_id,),
                )
            else:
                conn.execute(
                    "UPDATE strategy_test_batches SET status = 'failed', failure_reason = 'engine_failed' WHERE id = ?",
                    (affected_batch_id,),
                )
    finally:
        conn.close()

    payload = client.get(
        "/api/ai-strategy-recommendations",
        params={"end_date": "2026-07-13", "symbols": "MU"},
    ).json()

    assert payload["ranking_basis"] == "research_prior"
    assert payload["evidence_status"] == "partial"
    assert [item["template_key"] for item in payload["items"]] == RESEARCH_ORDER
    affected_item = next(item for item in payload["items"] if item["template_key"] == affected_template)
    assert affected_item["expectation"]["status"] == "partial"
    assert expected_reason in affected_item["expectation"]["failure_reasons"]


def test_ai_strategy_recommendations_allow_explicitly_excluded_non_available_days(tmp_path: Path):
    db_path = tmp_path / "ai-strategy-excluded-days.db"
    client = TestClient(create_app(db_path))
    catalog = client.get(
        "/api/ai-strategy-recommendations",
        params={"end_date": "2026-07-13", "symbols": "MU"},
    ).json()

    conn = connect(db_path)
    initialize_database(conn)
    try:
        configs = {config["strategy_id"]: config for config in list_strategy_configs(conn)}
        for item in catalog["items"]:
            batch_id = f"batch_{item['template_key']}"
            _insert_test_batch(
                conn,
                batch_id=batch_id,
                strategy_id=item["strategy_id"],
                params_json=json.dumps(item["recommended_params"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                params_hash=item["recommended_params_hash"],
                template_version=configs[item["strategy_id"]]["template_version"],
                total_pnl=250.0,
                profit_factor=1.5,
            )
            with conn:
                conn.execute(
                    "UPDATE strategy_test_batches SET day_count = 11 WHERE id = ?",
                    (batch_id,),
                )
                conn.execute(
                    """
                    INSERT INTO strategy_test_day_results (
                        id, batch_id, trade_date, source_archive_id, bars_hash, strategy_run_id,
                        status, failure_reason, signal_count, total_pnl, win_rate, profit_factor,
                        closed_group_count, indicator_hash, created_at
                    ) VALUES (?, ?, '2026-07-12', NULL, 'missing_bars', NULL,
                        'non_available_archive', 'no_bars_returned', 0, 0, 0, NULL, 0, '', ?)
                    """,
                    (f"excluded_{batch_id}", batch_id, "2026-07-14T09:00:00+00:00"),
                )
    finally:
        conn.close()

    payload = client.get(
        "/api/ai-strategy-recommendations",
        params={"end_date": "2026-07-13", "symbols": "MU"},
    ).json()

    assert payload["ranking_basis"] == "local_backtest"
    assert payload["evidence_status"] == "verified"
    assert all(item["expectation"]["excluded_day_count"] == 1 for item in payload["items"])
    assert all(item["expectation"]["excluded_day_reasons"] == ["no_bars_returned:1"] for item in payload["items"])


def test_ai_strategy_recommendations_validate_fixed_capital_and_symbol_scope(tmp_path: Path):
    client = TestClient(create_app(tmp_path / "ai-strategy-validation.db"))

    wrong_capital = client.get(
        "/api/ai-strategy-recommendations",
        params={"end_date": "2026-07-13", "symbols": "MU", "initial_capital": 50000},
    )
    too_many_symbols = client.get(
        "/api/ai-strategy-recommendations",
        params={"end_date": "2026-07-13", "symbols": ",".join(f"S{index}" for index in range(21))},
    )

    assert wrong_capital.status_code == 422
    assert too_many_symbols.status_code == 422
    assert too_many_symbols.json()["detail"] == "strategy_symbol_count_out_of_range"


def _insert_test_batch(
    conn,
    *,
    batch_id: str,
    strategy_id: str,
    params_json: str,
    params_hash: str,
    template_version: str,
    total_pnl: float,
    profit_factor: float,
) -> None:
    created_at = "2026-07-14T09:00:00+00:00"
    with conn:
        conn.execute(
            """
            INSERT INTO strategy_test_batches (
                id, strategy_id, provider, symbol, end_date, window_trading_days,
                archive_scope_hash, params_json, params_hash, template_version,
                indicator_engine_version, status, failure_reason, day_count,
                available_day_count, completed_day_count, signal_count, total_pnl,
                win_rate, profit_factor, max_drawdown, coverage_ratio, idempotency_key,
                created_at
            ) VALUES (?, ?, 'yahoo', 'MU', '2026-07-13', 30, ?, ?, ?, ?,
                'test_engine_v1', 'completed', NULL, 10, 10, 10, 20, ?,
                0.6, ?, 75.0, 0.333333, ?, ?)
            """,
            (
                batch_id,
                strategy_id,
                f"scope_{batch_id}",
                params_json,
                params_hash,
                template_version,
                total_pnl,
                profit_factor,
                f"key_{batch_id}",
                created_at,
            ),
        )
        for index in range(10):
            conn.execute(
                """
                INSERT INTO strategy_test_day_results (
                    id, batch_id, trade_date, source_archive_id, bars_hash, strategy_run_id,
                    status, failure_reason, signal_count, total_pnl, win_rate, profit_factor,
                    closed_group_count, indicator_hash, created_at
                ) VALUES (?, ?, ?, NULL, ?, NULL, 'completed', NULL, 2, ?, 0.6, ?, 1, ?, ?)
                """,
                (
                    f"day_{batch_id}_{index}",
                    batch_id,
                    f"2026-07-{index + 1:02d}",
                    f"bars_{batch_id}_{index}",
                    total_pnl / 10,
                    profit_factor,
                    f"indicator_{batch_id}_{index}",
                    created_at,
                ),
            )
