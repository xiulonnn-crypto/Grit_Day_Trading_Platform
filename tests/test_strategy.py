from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from grit_day_trading.api import create_app
from grit_day_trading.market_archive import archive_market_minutes
from grit_day_trading.market_provider import FakeMarketDataProvider
from grit_day_trading.service import import_stp_txt, list_fills
from grit_day_trading.storage import connect, initialize_database
from grit_day_trading.strategy import (
    BB_SQUEEZE_TEMPLATE_KEY,
    DEFAULT_BB_SQUEEZE_PARAMS,
    DEFAULT_BB_SQUEEZE_STRATEGY_ID,
    DEFAULT_LIQUIDITY_SWEEP_PARAMS,
    DEFAULT_LIQUIDITY_SWEEP_STRATEGY_ID,
    DEFAULT_MOMENTUM_MEAN_REVERSION_PARAMS,
    DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID,
    LIQUIDITY_SWEEP_TEMPLATE_KEY,
    MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY,
    _candidate_params_from_search_space,
    _default_optimization_search_space,
    _strategy_signal_performance,
    evaluate_bb_squeeze_breakout,
    evaluate_institutional_liquidity_sweep,
    evaluate_momentum_mean_reversion,
    list_strategy_configs,
    run_strategy_test_batch,
    run_strategy_signal_replay,
    update_strategy_config,
)


SAMPLE_PATH = Path("tests/fixtures/stp_sample.tsv")


def test_bb_squeeze_long_entry_and_risk_reward_exit():
    series, signals = evaluate_bb_squeeze_breakout(_long_breakout_bars())

    assert len(series) == len(_long_breakout_bars())
    assert [signal["action"] for signal in signals] == ["ENTRY_LONG", "EXIT_LONG"]
    entry, exit_signal = signals
    assert entry["bar_index"] == 60
    assert entry["price"] == 103.0
    assert entry["reason_codes"] == [
        "squeeze_setup",
        "vwap_above",
        "absolute_bandwidth_filter",
        "upper_band_breakout",
        "volume_spike",
        "rsi_momentum",
        "passive_take_profit_order",
    ]
    assert entry["metrics"]["absolute_bandwidth"] > entry["metrics"]["min_absolute_bandwidth"]
    assert entry["metrics"]["passive_take_profit_price"] == entry["take_profit_price"]
    assert entry["stop_loss_price"] < entry["price"] < entry["take_profit_price"]
    assert exit_signal["price"] == entry["take_profit_price"]
    assert exit_signal["reason_codes"] == ["risk_reward_target", "passive_take_profit_filled"]
    assert exit_signal["linked_entry_signal_index"] == 0


def test_bb_squeeze_short_entry_and_stop_exit():
    _, signals = evaluate_bb_squeeze_breakout(_short_breakout_bars())

    assert [signal["action"] for signal in signals] == ["ENTRY_SHORT", "EXIT_SHORT"]
    entry, exit_signal = signals
    assert entry["price"] == 97.0
    assert entry["stop_loss_price"] > entry["price"] > entry["take_profit_price"]
    assert "passive_take_profit_order" in entry["reason_codes"]
    assert exit_signal["reason_codes"] == ["stop_loss_hit"]
    assert exit_signal["linked_entry_signal_index"] == 0


def test_bb_squeeze_rejects_breakout_when_absolute_bandwidth_is_too_small():
    _, signals = evaluate_bb_squeeze_breakout(_long_breakout_bars(), {"min_absolute_bandwidth": 5.0})

    assert signals == []


def test_bb_squeeze_holds_pullback_inside_upper_band_until_exit_buffer_breaks():
    prefix = _long_breakout_bars()[:61]
    pullback_inside_upper = [*prefix, _bar(61, 103.0, 103.2, 102.0, 102.2, 500)]
    _, pullback_signals = evaluate_bb_squeeze_breakout(pullback_inside_upper)

    assert [signal["action"] for signal in pullback_signals] == ["ENTRY_LONG"]

    buffer_break = [*pullback_inside_upper, _bar(62, 102.2, 102.3, 101.1, 101.2, 450)]
    _, buffer_signals = evaluate_bb_squeeze_breakout(buffer_break)

    assert [signal["action"] for signal in buffer_signals] == ["ENTRY_LONG", "EXIT_LONG"]
    assert buffer_signals[-1]["reason_codes"] == ["exit_ema_breached"]
    assert "exit_ema" in buffer_signals[-1]["metrics"]


def test_bb_squeeze_does_not_emit_warmup_or_future_dependent_signals():
    warmup_only = _long_breakout_bars()[:25]
    _, warmup_signals = evaluate_bb_squeeze_breakout(warmup_only)
    assert warmup_signals == []

    prefix = _long_breakout_bars()[:61]
    optimistic_future = [*prefix, _bar(61, 103.0, 108.0, 102.8, 107.8, 500)]
    pessimistic_future = [*prefix, _bar(61, 103.0, 103.2, 99.0, 100.0, 500)]
    _, optimistic_signals = evaluate_bb_squeeze_breakout(optimistic_future)
    _, pessimistic_signals = evaluate_bb_squeeze_breakout(pessimistic_future)

    assert optimistic_signals[0] == pessimistic_signals[0]
    assert optimistic_signals[0]["action"] == "ENTRY_LONG"


def test_strategy_signal_performance_summarizes_closed_groups():
    performance = _strategy_signal_performance(
        [
            {
                "id": "signal-entry-long",
                "signal_id": "signal-entry-long",
                "timestamp": "2026-06-01T10:00:00",
                "bar_index": 1,
                "side": "LONG",
                "action": "ENTRY_LONG",
                "price": 100.0,
                "linked_entry_signal_id": None,
            },
            {
                "id": "signal-exit-long",
                "signal_id": "signal-exit-long",
                "timestamp": "2026-06-01T10:05:00",
                "bar_index": 5,
                "side": "LONG",
                "action": "EXIT_LONG",
                "price": 104.0,
                "linked_entry_signal_id": "signal-entry-long",
                "metrics": {"exit_fraction": 0.5},
            },
            {
                "id": "signal-exit-long-final",
                "signal_id": "signal-exit-long-final",
                "timestamp": "2026-06-01T10:08:00",
                "bar_index": 8,
                "side": "LONG",
                "action": "EXIT_LONG",
                "price": 106.0,
                "linked_entry_signal_id": "signal-entry-long",
                "metrics": {"exit_fraction": 0.5},
            },
            {
                "id": "signal-entry-short",
                "signal_id": "signal-entry-short",
                "timestamp": "2026-06-01T11:00:00",
                "bar_index": 10,
                "side": "SHORT",
                "action": "ENTRY_SHORT",
                "price": 50.0,
                "linked_entry_signal_id": None,
            },
            {
                "id": "signal-exit-short",
                "signal_id": "signal-exit-short",
                "timestamp": "2026-06-01T11:04:00",
                "bar_index": 14,
                "side": "SHORT",
                "action": "EXIT_SHORT",
                "price": 53.0,
                "linked_entry_signal_id": "signal-entry-short",
            },
            {
                "id": "signal-open-long",
                "signal_id": "signal-open-long",
                "timestamp": "2026-06-01T12:00:00",
                "bar_index": 20,
                "side": "LONG",
                "action": "ENTRY_LONG",
                "price": 80.0,
                "linked_entry_signal_id": None,
            },
        ]
    )

    assert performance["unit"] == "price_delta_weighted_by_exit_fraction"
    assert performance["total_pnl"] == 2.0
    assert performance["gross_profit"] == 5.0
    assert performance["gross_loss"] == -3.0
    assert performance["closed_group_count"] == 2
    assert performance["winning_group_count"] == 1
    assert performance["losing_group_count"] == 1
    assert performance["win_rate"] == 0.5
    assert performance["profit_factor"] == 1.666667


def test_liquidity_sweep_long_entry_and_oco_take_profit_exit():
    series, signals = evaluate_institutional_liquidity_sweep(_liquidity_sweep_long_bars())

    assert len(series) == len(_liquidity_sweep_long_bars())
    assert [signal["action"] for signal in signals] == ["ENTRY_LONG", "EXIT_LONG"]
    entry, exit_signal = signals
    assert entry["bar_index"] == 20
    assert entry["reason_codes"] == [
        "liquidity_sweep_setup",
        "vwap_above",
        "local_low_swept",
        "pin_bar_reclaim",
        "volume_spike",
        "oco_immediate_mode",
        "passive_take_profit_order",
    ]
    assert entry["metrics"]["shadow_ratio"] >= entry["metrics"]["required_shadow_ratio"]
    assert entry["metrics"]["sweep_distance"] > 0
    assert entry["stop_loss_price"] < entry["price"] < entry["take_profit_price"]
    assert exit_signal["price"] == entry["take_profit_price"]
    assert exit_signal["reason_codes"] == ["risk_reward_target", "passive_take_profit_filled"]
    assert exit_signal["linked_entry_signal_index"] == 0


def test_liquidity_sweep_short_entry_and_stop_exit():
    _, signals = evaluate_institutional_liquidity_sweep(_liquidity_sweep_short_bars())

    assert [signal["action"] for signal in signals] == ["ENTRY_SHORT", "EXIT_SHORT"]
    entry, exit_signal = signals
    assert entry["reason_codes"] == [
        "liquidity_sweep_setup",
        "vwap_below",
        "local_high_swept",
        "pin_bar_reject",
        "volume_spike",
        "oco_immediate_mode",
        "passive_take_profit_order",
    ]
    assert entry["stop_loss_price"] > entry["price"] > entry["take_profit_price"]
    assert exit_signal["reason_codes"] == ["stop_loss_hit"]
    assert exit_signal["linked_entry_signal_index"] == 0


def test_liquidity_sweep_rejects_weak_shadow_reclaim():
    weak_shadow = _liquidity_sweep_long_bars()
    weak_shadow[20] = _bar(20, 100.7, 102.1, 99.9, 101.2, 400)

    _, signals = evaluate_institutional_liquidity_sweep(weak_shadow, {"shadow_ratio": 0.7})

    assert signals == []


def test_momentum_mean_reversion_long_entry_partial_and_final_exit():
    bars = _mean_reversion_long_bars()
    context = {
        "QQQ": _momentum_context_bars("up"),
        "SMH": _momentum_context_bars("up"),
    }
    series, signals = evaluate_momentum_mean_reversion(bars, context)

    assert len(series) == len(bars)
    assert [signal["action"] for signal in signals] == ["ENTRY_LONG", "EXIT_LONG", "EXIT_LONG"]
    entry, partial_exit, final_exit = signals
    assert entry["bar_index"] == 20
    assert entry["reason_codes"] == [
        "time_window_1130_1330",
        "regime_chop_adx",
        "momentum_filter_long",
        "lower_band_observation",
        "reversal_reclaim_lower_band",
        "pin_bar_reclaim",
        "atr_dynamic_stop",
        "partial_take_profit_plan",
        "break_even_after_middle_target",
    ]
    assert entry["price"] == 98.8
    assert entry["stop_loss_price"] == round(
        entry["price"] - entry["metrics"]["atr"] * entry["metrics"]["atr_stop_multiplier"],
        6,
    )
    assert entry["metrics"]["adx"] < entry["metrics"]["adx_chop_threshold"]
    assert entry["metrics"]["market_regime_code"] == 1.0
    assert entry["metrics"]["qqq_close"] > entry["metrics"]["qqq_vwap"]
    assert entry["metrics"]["smh_close"] > entry["metrics"]["smh_vwap"]
    assert partial_exit["reason_codes"] == ["middle_band_first_target", "partial_take_profit_filled", "break_even_stop_armed"]
    assert partial_exit["metrics"]["exit_fraction"] == 0.5
    assert partial_exit["stop_loss_price"] == entry["price"]
    assert final_exit["reason_codes"] == ["upper_band_final_target", "remaining_take_profit_filled"]
    assert final_exit["linked_entry_signal_index"] == 0


def test_momentum_mean_reversion_requires_time_window_and_context_direction():
    outside_window = _mean_reversion_long_bars()
    for index, bar in enumerate(outside_window):
        bar["timestamp"] = f"2026-06-01T10:{index:02d}:00"

    _, time_filtered = evaluate_momentum_mean_reversion(
        outside_window,
        {
            "QQQ": _momentum_context_bars("up", start_hour=10, start_minute=0),
            "SMH": _momentum_context_bars("up", start_hour=10, start_minute=0),
        },
    )
    _, context_filtered = evaluate_momentum_mean_reversion(
        _mean_reversion_long_bars(),
        {"QQQ": _momentum_context_bars("down"), "SMH": _momentum_context_bars("up")},
    )

    assert time_filtered == []
    assert context_filtered == []


def test_momentum_mean_reversion_suppresses_entries_when_adx_trends():
    bars = _mean_reversion_trend_day_long_bars()
    context = {
        "QQQ": _momentum_context_bars("up"),
        "SMH": _momentum_context_bars("up"),
    }

    series, signals = evaluate_momentum_mean_reversion(bars, context)

    assert signals == []
    assert series[20]["time_window"] == 1
    assert series[20]["momentum_long"] == 1
    assert series[20]["adx"] > 25
    assert series[20]["market_regime"] == "trend"
    assert series[20]["mean_reversion_enabled"] == 0


def test_momentum_mean_reversion_short_entry_partial_and_final_exit():
    bars = _mean_reversion_short_bars()
    context = {
        "QQQ": _momentum_context_bars("down"),
        "SMH": _momentum_context_bars("down"),
    }
    _, signals = evaluate_momentum_mean_reversion(bars, context)

    assert [signal["action"] for signal in signals] == ["ENTRY_SHORT", "EXIT_SHORT", "EXIT_SHORT"]
    entry, partial_exit, final_exit = signals
    assert entry["bar_index"] == 20
    assert entry["reason_codes"] == [
        "time_window_1130_1330",
        "regime_chop_adx",
        "momentum_filter_short",
        "upper_band_observation",
        "reversal_reject_upper_band",
        "pin_bar_reject",
        "atr_dynamic_stop",
        "partial_take_profit_plan",
        "break_even_after_middle_target",
    ]
    assert entry["stop_loss_price"] > entry["price"] > entry["take_profit_price"]
    assert entry["stop_loss_price"] == round(
        entry["price"] + entry["metrics"]["atr"] * entry["metrics"]["atr_stop_multiplier"],
        6,
    )
    assert entry["metrics"]["adx"] < entry["metrics"]["adx_chop_threshold"]
    assert partial_exit["reason_codes"] == ["middle_band_first_target", "partial_take_profit_filled", "break_even_stop_armed"]
    assert partial_exit["stop_loss_price"] == entry["price"]
    assert final_exit["reason_codes"] == ["lower_band_final_target", "remaining_take_profit_filled"]


def test_strategy_replay_persists_source_archive_hash_and_is_idempotent(tmp_path):
    conn = connect(tmp_path / "strategy.db")
    try:
        initialize_database(conn)
        import_stp_txt(conn, "sample.tsv", SAMPLE_PATH.read_bytes())
        update_strategy_config(conn, DEFAULT_BB_SQUEEZE_STRATEGY_ID, enabled=True)
        archive = archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-01",
            source_fill_count=2,
            provider=FakeMarketDataProvider(minute_bars={"AAPL": _long_breakout_bars()}),
        )
        before_prices = [fill["price"] for fill in list_fills(conn, date="2026-06-01")]

        first = run_strategy_signal_replay(
            conn,
            strategy_id=DEFAULT_BB_SQUEEZE_STRATEGY_ID,
            trade_date="2026-06-01",
            symbol="AAPL",
        )
        second = run_strategy_signal_replay(
            conn,
            strategy_id=DEFAULT_BB_SQUEEZE_STRATEGY_ID,
            trade_date="2026-06-01",
            symbol="AAPL",
        )
        forced = run_strategy_signal_replay(
            conn,
            strategy_id=DEFAULT_BB_SQUEEZE_STRATEGY_ID,
            trade_date="2026-06-01",
            symbol="AAPL",
            force=True,
        )

        assert first["run_id"] == second["run_id"] == forced["run_id"]
        assert first["status"] == "completed"
        assert first["source_archive_id"] == archive["archive_id"]
        assert first["bars_hash"] == archive["bars_hash"]
        assert len(first["indicator_hash"]) == 64
        assert first["signal_count"] == 2
        assert [signal["action"] for signal in first["signals"]] == ["ENTRY_LONG", "EXIT_LONG"]
        assert first["signal_performance"]["closed_group_count"] == 1
        assert first["signal_performance"]["winning_group_count"] == 1
        assert first["signal_performance"]["win_rate"] == 1.0
        assert first["signal_performance"]["total_pnl"] > 0
        assert conn.execute("SELECT COUNT(*) FROM strategy_signal_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM strategy_signals").fetchone()[0] == 2
        assert [fill["price"] for fill in list_fills(conn, date="2026-06-01")] == before_prices
    finally:
        conn.close()


def test_liquidity_sweep_strategy_replay_persists_archive_and_preserves_fills(tmp_path):
    conn = connect(tmp_path / "liquidity_sweep.db")
    try:
        initialize_database(conn)
        import_stp_txt(conn, "sample.tsv", SAMPLE_PATH.read_bytes())
        update_strategy_config(conn, DEFAULT_LIQUIDITY_SWEEP_STRATEGY_ID, enabled=True)
        archive = archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-01",
            source_fill_count=2,
            provider=FakeMarketDataProvider(minute_bars={"AAPL": _liquidity_sweep_long_bars()}),
        )
        before_prices = [fill["price"] for fill in list_fills(conn, date="2026-06-01")]

        run = run_strategy_signal_replay(
            conn,
            strategy_id=DEFAULT_LIQUIDITY_SWEEP_STRATEGY_ID,
            trade_date="2026-06-01",
            symbol="AAPL",
        )

        assert run["status"] == "completed"
        assert run["source_archive_id"] == archive["archive_id"]
        assert run["bars_hash"] == archive["bars_hash"]
        assert run["indicator_engine_version"] == "strategy_indicator_engine_liquidity_sweep_v1"
        assert run["strategy"]["template_key"] == "institutional_liquidity_sweep_v1"
        assert [signal["action"] for signal in run["signals"]] == ["ENTRY_LONG", "EXIT_LONG"]
        assert [fill["price"] for fill in list_fills(conn, date="2026-06-01")] == before_prices
    finally:
        conn.close()


def test_momentum_mean_reversion_replay_requires_context_archives_and_preserves_fills(tmp_path):
    conn = connect(tmp_path / "momentum_mean_reversion.db")
    try:
        initialize_database(conn)
        import_stp_txt(conn, "sample.tsv", SAMPLE_PATH.read_bytes())
        update_strategy_config(conn, DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID, enabled=True)
        target_archive = archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-01",
            source_fill_count=2,
            provider=FakeMarketDataProvider(minute_bars={"AAPL": _mean_reversion_long_bars()}),
        )

        missing_context = run_strategy_signal_replay(
            conn,
            strategy_id=DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID,
            trade_date="2026-06-01",
            symbol="AAPL",
        )
        assert missing_context["status"] == "missing_archive"
        assert missing_context["source_archive_id"] == target_archive["archive_id"]
        assert "momentum_context_archive_required:QQQ,SMH" == missing_context["failure_reason"]

        archive_market_minutes(
            conn,
            symbol="QQQ",
            trade_date="2026-06-01",
            source_fill_count=0,
            provider=FakeMarketDataProvider(minute_bars={"QQQ": _momentum_context_bars("up")}),
        )
        archive_market_minutes(
            conn,
            symbol="SMH",
            trade_date="2026-06-01",
            source_fill_count=0,
            provider=FakeMarketDataProvider(minute_bars={"SMH": _momentum_context_bars("up")}),
        )
        before_prices = [fill["price"] for fill in list_fills(conn, date="2026-06-01")]

        completed = run_strategy_signal_replay(
            conn,
            strategy_id=DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID,
            trade_date="2026-06-01",
            symbol="AAPL",
        )
        repeated = run_strategy_signal_replay(
            conn,
            strategy_id=DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID,
            trade_date="2026-06-01",
            symbol="AAPL",
        )

        assert completed["run_id"] == repeated["run_id"]
        assert completed["status"] == "completed"
        assert completed["source_archive_id"] == target_archive["archive_id"]
        assert completed["bars_hash"] != target_archive["bars_hash"]
        assert completed["indicator_engine_version"] == "strategy_indicator_engine_momentum_mean_reversion_v2"
        assert completed["strategy"]["template_key"] == "momentum_mean_reversion_v1"
        assert [signal["action"] for signal in completed["signals"]] == ["ENTRY_LONG", "EXIT_LONG", "EXIT_LONG"]
        assert [fill["price"] for fill in list_fills(conn, date="2026-06-01")] == before_prices
    finally:
        conn.close()


def test_strategy_api_creates_enables_runs_and_surfaces_missing_archive(tmp_path):
    db_path = tmp_path / "api.db"

    with TestClient(create_app(db_path)) as client:
        templates = client.get("/api/strategy-templates").json()["items"]
        mean_reversion_template = next(template for template in templates if template["template_key"] == "momentum_mean_reversion_v1")
        strategies = client.get("/api/strategies").json()["items"]
        default_strategy = next(strategy for strategy in strategies if strategy["template_key"] == "bb_squeeze_breakout_v1")
        liquidity_strategy = next(strategy for strategy in strategies if strategy["template_key"] == "institutional_liquidity_sweep_v1")
        mean_reversion_strategy = next(strategy for strategy in strategies if strategy["template_key"] == "momentum_mean_reversion_v1")
        disabled = client.post(
            f"/api/strategies/{default_strategy['strategy_id']}/runs",
            json={"date": "2026-06-01", "symbol": "AAPL", "provider": "yahoo"},
        ).json()
        enabled = client.patch(
            f"/api/strategies/{default_strategy['strategy_id']}",
            json={"enabled": True},
        ).json()
        missing = client.post(
            f"/api/strategies/{default_strategy['strategy_id']}/runs",
            json={"date": "2026-06-01", "symbol": "AAPL", "provider": "yahoo"},
        ).json()
        created = client.post(
            "/api/strategies",
            json={"name": "BB 副本", "template_key": "bb_squeeze_breakout_v1", "params": {"risk_reward": 3}},
        ).json()
        created_liquidity = client.post(
            "/api/strategies",
            json={"name": "Sweep 副本", "template_key": "institutional_liquidity_sweep_v1", "params": {"local_window": 20}},
        ).json()
        created_mean_reversion = client.post(
            "/api/strategies",
            json={"name": "MR 副本", "template_key": "momentum_mean_reversion_v1", "params": {"atr_stop_multiplier": 2}},
        ).json()

    assert templates[0]["template_key"] == "bb_squeeze_breakout_v1"
    assert {template["template_key"] for template in templates} == {
        "bb_squeeze_breakout_v1",
        "institutional_liquidity_sweep_v1",
        "momentum_mean_reversion_v1",
    }
    assert {param["key"] for param in templates[0]["param_schema"]} >= {"exit_ema_period", "min_absolute_bandwidth"}
    assert {param["key"] for param in mean_reversion_template["param_schema"]} >= {
        "adx_period",
        "adx_trend_threshold",
        "adx_chop_threshold",
        "atr_period",
        "atr_stop_multiplier",
    }
    assert default_strategy["enabled"] is False
    assert default_strategy["params"]["exit_ema_period"] == 9
    assert default_strategy["params"]["min_absolute_bandwidth"] == 2.0
    assert liquidity_strategy["enabled"] is False
    assert liquidity_strategy["params"]["exit_type"] == "OCO_Immediate"
    assert liquidity_strategy["params"]["local_window"] == 20
    assert liquidity_strategy["params"]["shadow_ratio"] == 0.6
    assert mean_reversion_strategy["enabled"] is False
    assert mean_reversion_strategy["params"]["momentum_context"] == "QQQ_SMH"
    assert mean_reversion_strategy["params"]["start_hour"] == 11
    assert mean_reversion_strategy["params"]["start_minute"] == 30
    assert mean_reversion_strategy["params"]["end_hour"] == 13
    assert mean_reversion_strategy["params"]["end_minute"] == 30
    assert mean_reversion_strategy["params"]["adx_period"] == 14
    assert mean_reversion_strategy["params"]["adx_trend_threshold"] == 25.0
    assert mean_reversion_strategy["params"]["adx_chop_threshold"] == 20.0
    assert mean_reversion_strategy["params"]["atr_period"] == 14
    assert mean_reversion_strategy["params"]["atr_stop_multiplier"] == 1.5
    assert disabled["status"] == "strategy_disabled"
    assert enabled["enabled"] is True
    assert missing["status"] == "missing_archive"
    assert created["enabled"] is False
    assert created["params"]["risk_reward"] == 3.0
    assert created_liquidity["params"]["exit_type"] == "OCO_Immediate"
    assert created_mean_reversion["params"]["atr_stop_multiplier"] == 2.0

    conn = connect(db_path)
    try:
        initialize_database(conn)
        import_stp_txt(conn, "sample.tsv", SAMPLE_PATH.read_bytes())
        archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-01",
            source_fill_count=2,
            provider=FakeMarketDataProvider(minute_bars={"AAPL": _long_breakout_bars()}),
        )
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        completed = client.post(
            f"/api/strategies/{default_strategy['strategy_id']}/runs",
            json={"date": "2026-06-01", "symbol": "AAPL", "provider": "yahoo"},
        ).json()
        repeated = client.post(
            f"/api/strategies/{default_strategy['strategy_id']}/runs",
            json={"date": "2026-06-01", "symbol": "AAPL", "provider": "yahoo"},
        ).json()
        runs = client.get(
            f"/api/strategy-runs?date=2026-06-01&symbol=AAPL&strategy_id={default_strategy['strategy_id']}"
        ).json()["items"]

    assert completed["status"] == "completed"
    assert completed["run_id"] == repeated["run_id"]
    assert completed["signal_count"] == 2
    assert completed["signal_performance"]["closed_group_count"] == 1
    assert completed["signal_performance"]["winning_group_count"] == 1
    assert any(run["status"] == "completed" for run in runs)


def test_strategy_test_batch_uses_archived_minutes_and_preserves_fills(tmp_path):
    conn = connect(tmp_path / "strategy_test_batch.db")
    try:
        initialize_database(conn)
        import_stp_txt(conn, "sample.tsv", SAMPLE_PATH.read_bytes())
        before_prices = [fill["price"] for fill in list_fills(conn, date="2026-06-01")]
        update_strategy_config(conn, DEFAULT_BB_SQUEEZE_STRATEGY_ID, enabled=True)
        for trade_date in ("2026-06-01", "2026-06-02"):
            archive_market_minutes(
                conn,
                symbol="AAPL",
                trade_date=trade_date,
                source_fill_count=2,
                provider=FakeMarketDataProvider(minute_bars={"AAPL": _long_breakout_bars()}),
            )
        archive_count = conn.execute("SELECT COUNT(*) FROM market_minute_archives").fetchone()[0]

        batch = run_strategy_test_batch(
            conn,
            strategy_id=DEFAULT_BB_SQUEEZE_STRATEGY_ID,
            end_date="2026-06-02",
            symbol="AAPL",
            window_trading_days=2,
        )
        repeated = run_strategy_test_batch(
            conn,
            strategy_id=DEFAULT_BB_SQUEEZE_STRATEGY_ID,
            end_date="2026-06-02",
            symbol="AAPL",
            window_trading_days=2,
        )

        assert batch["batch_id"] == repeated["batch_id"]
        assert batch["status"] == "completed"
        assert batch["day_count"] == 2
        assert batch["completed_day_count"] == 2
        assert batch["signal_count"] == 4
        assert batch["coverage_ratio"] == 1.0
        assert all(day["status"] == "completed" for day in batch["day_results"])
        assert conn.execute("SELECT COUNT(*) FROM market_minute_archives").fetchone()[0] == archive_count
        assert [fill["price"] for fill in list_fills(conn, date="2026-06-01")] == before_prices
    finally:
        conn.close()


def test_strategy_test_batch_surfaces_archive_coverage_and_status_failures(tmp_path):
    db_path = tmp_path / "strategy_test_api.db"
    conn = connect(db_path)
    try:
        initialize_database(conn)
        update_strategy_config(conn, DEFAULT_BB_SQUEEZE_STRATEGY_ID, enabled=True)
        archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-01",
            source_fill_count=1,
            provider=FakeMarketDataProvider(minute_bars={"AAPL": _long_breakout_bars()}),
        )
        archive_market_minutes(
            conn,
            symbol="MSFT",
            trade_date="2026-06-01",
            source_fill_count=1,
            provider=FakeMarketDataProvider(minute_status={"MSFT": "provider_failed"}),
        )
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        strategies = client.get("/api/strategies").json()["items"]
        strategy = next(item for item in strategies if item["strategy_id"] == DEFAULT_BB_SQUEEZE_STRATEGY_ID)
        insufficient = client.post(
            f"/api/strategies/{strategy['strategy_id']}/test-runs",
            json={"end_date": "2026-06-02", "symbol": "AAPL", "provider": "yahoo", "window_trading_days": 2},
        ).json()
        non_available = client.post(
            f"/api/strategies/{strategy['strategy_id']}/test-runs",
            json={"end_date": "2026-06-01", "symbol": "MSFT", "provider": "yahoo", "window_trading_days": 1},
        ).json()
        listed = client.get(
            f"/api/strategy-test-runs?end_date=2026-06-02&symbol=AAPL&strategy_id={strategy['strategy_id']}"
        ).json()["items"]

    assert insufficient["status"] == "insufficient_archive_coverage"
    assert insufficient["failure_reason"] == "required_2_archived_trading_days_found_1"
    assert insufficient["day_count"] == 1
    assert listed[0]["batch_id"] == insufficient["batch_id"]
    assert non_available["status"] == "completed"
    assert non_available["completed_day_count"] == 0
    assert non_available["day_results"][0]["status"] == "non_available_archive"
    assert non_available["day_results"][0]["failure_reason"] == "fake_provider_failed"


def test_strategy_optimization_ranks_candidates_and_does_not_patch_config(tmp_path):
    db_path = tmp_path / "strategy_optimization.db"
    conn = connect(db_path)
    try:
        initialize_database(conn)
        update_strategy_config(conn, DEFAULT_BB_SQUEEZE_STRATEGY_ID, enabled=True)
        for trade_date in ("2026-06-01", "2026-06-02"):
            archive_market_minutes(
                conn,
                symbol="AAPL",
                trade_date=trade_date,
                source_fill_count=2,
                provider=FakeMarketDataProvider(minute_bars={"AAPL": _long_breakout_bars()}),
            )
        before_strategy = next(
            item for item in list_strategy_configs(conn) if item["strategy_id"] == DEFAULT_BB_SQUEEZE_STRATEGY_ID
        )
    finally:
        conn.close()

    search_space = {
        "volume_multiplier": [2.0],
        "squeeze_percentile": [10.0],
        "risk_reward": [2.0],
        "min_absolute_bandwidth": [2.0],
    }
    with TestClient(create_app(db_path)) as client:
        optimization = client.post(
            f"/api/strategies/{DEFAULT_BB_SQUEEZE_STRATEGY_ID}/optimizations",
            json={
                "end_date": "2026-06-02",
                "symbol": "AAPL",
                "provider": "yahoo",
                "window_trading_days": 2,
                "search_space": search_space,
            },
        ).json()
        repeated = client.post(
            f"/api/strategies/{DEFAULT_BB_SQUEEZE_STRATEGY_ID}/optimizations",
            json={
                "end_date": "2026-06-02",
                "symbol": "AAPL",
                "provider": "yahoo",
                "window_trading_days": 2,
                "search_space": search_space,
            },
        ).json()
        listed = client.get(
            f"/api/strategy-optimizations?end_date=2026-06-02&symbol=AAPL&strategy_id={DEFAULT_BB_SQUEEZE_STRATEGY_ID}"
        ).json()["items"]
        after_strategy = next(
            item
            for item in client.get("/api/strategies").json()["items"]
            if item["strategy_id"] == DEFAULT_BB_SQUEEZE_STRATEGY_ID
        )

    assert optimization["optimization_id"] == repeated["optimization_id"]
    assert optimization["status"] == "completed"
    assert optimization["candidate_count"] == 1
    assert optimization["eligible_candidate_count"] == 1
    assert optimization["best_candidate_id"] == optimization["candidates"][0]["candidate_id"]
    assert optimization["candidates"][0]["rank"] == 1
    assert optimization["candidates"][0]["status"] == "eligible"
    assert optimization["candidates"][0]["coverage_ratio"] == 1.0
    assert listed[0]["optimization_id"] == optimization["optimization_id"]
    assert listed[0]["candidates"] == []
    assert after_strategy["params_hash"] == before_strategy["params_hash"]


def test_strategy_optimization_rejects_candidate_cap(tmp_path):
    db_path = tmp_path / "strategy_optimization_cap.db"
    with TestClient(create_app(db_path)) as client:
        strategy = next(
            item
            for item in client.get("/api/strategies").json()["items"]
            if item["strategy_id"] == DEFAULT_BB_SQUEEZE_STRATEGY_ID
        )
        client.patch(f"/api/strategies/{strategy['strategy_id']}", json={"enabled": True})
        response = client.post(
            f"/api/strategies/{strategy['strategy_id']}/optimizations",
            json={
                "end_date": "2026-06-02",
                "symbol": "AAPL",
                "provider": "yahoo",
                "window_trading_days": 1,
                "search_space": {
                    "volume_multiplier": [1, 2, 3, 4],
                    "squeeze_percentile": [5, 10, 15, 20],
                    "risk_reward": [1, 2, 3, 4],
                    "min_absolute_bandwidth": [1, 2, 3, 4],
                },
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "strategy_optimization_candidate_cap_exceeded"


def test_momentum_default_optimization_search_space_skips_invalid_adx_threshold_pairs():
    candidates = _candidate_params_from_search_space(
        DEFAULT_MOMENTUM_MEAN_REVERSION_PARAMS,
        _default_optimization_search_space(MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY),
        allow_sampling=True,
        template_key=MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY,
    )

    assert len(candidates) == 120
    assert all(candidate["adx_chop_threshold"] < candidate["adx_trend_threshold"] for candidate in candidates)
    assert any(candidate["adx_trend_threshold"] == 20.0 for candidate in candidates)
    assert any(candidate["adx_chop_threshold"] == 20.0 for candidate in candidates)
    assert any(candidate["swing_lookback"] == 5 for candidate in candidates)


@pytest.mark.parametrize(
    ("template_key", "base_params", "expected_keys"),
    [
        (
            BB_SQUEEZE_TEMPLATE_KEY,
            DEFAULT_BB_SQUEEZE_PARAMS,
            {"volume_multiplier", "squeeze_percentile", "risk_reward", "min_absolute_bandwidth", "setup_minutes"},
        ),
        (
            LIQUIDITY_SWEEP_TEMPLATE_KEY,
            DEFAULT_LIQUIDITY_SWEEP_PARAMS,
            {"local_window", "shadow_ratio", "volume_multiplier", "risk_reward", "max_holding_bars"},
        ),
        (
            MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY,
            DEFAULT_MOMENTUM_MEAN_REVERSION_PARAMS,
            {"adx_trend_threshold", "adx_chop_threshold", "atr_stop_multiplier", "pin_shadow_ratio", "swing_lookback"},
        ),
    ],
)
def test_default_optimization_search_spaces_sample_to_candidate_cap(template_key, base_params, expected_keys):
    search_space = _default_optimization_search_space(template_key)
    candidates = _candidate_params_from_search_space(
        base_params,
        search_space,
        allow_sampling=True,
        template_key=template_key,
    )

    assert set(search_space) == expected_keys
    assert len(candidates) == 120
    for key, values in search_space.items():
        observed = {candidate[key] for candidate in candidates}
        assert observed == set(values)


def test_momentum_optimization_default_search_space_returns_coverage_status_not_adx_error(tmp_path):
    db_path = tmp_path / "momentum_optimization_default.db"
    with TestClient(create_app(db_path)) as client:
        client.patch(f"/api/strategies/{DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID}", json={"enabled": True})
        response = client.post(
            f"/api/strategies/{DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID}/optimizations",
            json={
                "end_date": "2026-06-04",
                "symbol": "MU",
                "provider": "yahoo",
                "window_trading_days": 30,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "insufficient_archive_coverage"
    assert payload["failure_reason"] == "required_30_archived_trading_days_found_0"


def test_momentum_strategy_test_batch_records_missing_context_archives(tmp_path):
    conn = connect(tmp_path / "momentum_strategy_test.db")
    try:
        initialize_database(conn)
        update_strategy_config(conn, DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID, enabled=True)
        archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-01",
            source_fill_count=2,
            provider=FakeMarketDataProvider(minute_bars={"AAPL": _long_breakout_bars()}),
        )
        batch = run_strategy_test_batch(
            conn,
            strategy_id=DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID,
            end_date="2026-06-01",
            symbol="AAPL",
            window_trading_days=1,
        )
    finally:
        conn.close()

    assert batch["status"] == "completed"
    assert batch["completed_day_count"] == 0
    assert batch["day_results"][0]["status"] == "missing_archive"
    assert batch["day_results"][0]["failure_reason"].startswith("momentum_context_archive_required:")


def test_strategy_configs_backfill_new_bb_params_for_legacy_rows(tmp_path):
    conn = connect(tmp_path / "legacy_strategy.db")
    try:
        initialize_database(conn)
        with conn:
            conn.execute("DELETE FROM strategy_configs")
            conn.execute(
                """
                INSERT INTO strategy_configs (
                    id, name, template_key, template_version, enabled,
                    params_json, params_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    "strategy_legacy",
                    "Legacy BB",
                    "bb_squeeze_breakout_v1",
                    "bb_squeeze_breakout_v1",
                    '{"risk_reward":2.0}',
                    "old_hash",
                    "2026-06-01T00:00:00Z",
                    "2026-06-01T00:00:00Z",
                ),
            )

        strategy = list_strategy_configs(conn)[0]
        stored = conn.execute("SELECT template_version, params_hash FROM strategy_configs WHERE id = ?", ("strategy_legacy",)).fetchone()

        assert strategy["template_version"] == "bb_squeeze_breakout_v1.1"
        assert strategy["params"]["exit_ema_period"] == 9
        assert strategy["params"]["min_absolute_bandwidth"] == 2.0
        assert strategy["params_hash"] != "old_hash"
        assert stored["template_version"] == strategy["template_version"]
        assert stored["params_hash"] == strategy["params_hash"]
    finally:
        conn.close()


def test_strategy_configs_backfill_momentum_regime_params_and_strict_window(tmp_path):
    conn = connect(tmp_path / "legacy_momentum_strategy.db")
    try:
        initialize_database(conn)
        with conn:
            conn.execute("DELETE FROM strategy_configs")
            conn.execute(
                """
                INSERT INTO strategy_configs (
                    id, name, template_key, template_version, enabled,
                    params_json, params_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    "strategy_legacy_mr",
                    "Legacy MR",
                    "momentum_mean_reversion_v1",
                    "momentum_mean_reversion_v1.0",
                    '{"bb_period":20,"bb_stddev":2.0,"start_hour":11,"start_minute":0,"end_hour":14,"end_minute":30,"pin_shadow_ratio":0.55,"swing_lookback":3,"tick_size":0.01,"stop_tick_offset":4,"first_target_exit_fraction":0.5,"momentum_context":"QQQ_SMH"}',
                    "old_hash",
                    "2026-06-01T00:00:00Z",
                    "2026-06-01T00:00:00Z",
                ),
            )

        strategy = list_strategy_configs(conn)[0]

        assert strategy["template_version"] == "momentum_mean_reversion_v1.1"
        assert strategy["params"]["start_hour"] == 11
        assert strategy["params"]["start_minute"] == 30
        assert strategy["params"]["end_hour"] == 13
        assert strategy["params"]["end_minute"] == 30
        assert strategy["params"]["adx_trend_threshold"] == 25.0
        assert strategy["params"]["adx_chop_threshold"] == 20.0
        assert strategy["params"]["atr_stop_multiplier"] == 1.5
        assert "stop_tick_offset" not in strategy["params"]
    finally:
        conn.close()


def _long_breakout_bars():
    bars = []
    for index in range(25):
        close = 99.0 if index % 2 == 0 else 101.0
        bars.append(_bar(index, close - 0.1, close + 0.3, close - 0.3, close, 100))
    for step in range(35):
        close = 100.5 + step * 0.002
        bars.append(_bar(len(bars), close - 0.001, close + 0.01, close - 0.01, close, 100))
    bars.append(_bar(len(bars), 100.6, 103.2, 100.55, 103.0, 300))
    bars.append(_bar(len(bars), 103.0, 108.0, 102.8, 107.8, 500))
    return bars


def _short_breakout_bars():
    bars = []
    for index in range(25):
        close = 99.0 if index % 2 == 0 else 101.0
        bars.append(_bar(index, close + 0.1, close + 0.3, close - 0.3, close, 100))
    for step in range(35):
        close = 99.5 - step * 0.002
        bars.append(_bar(len(bars), close + 0.001, close + 0.01, close - 0.01, close, 100))
    bars.append(_bar(len(bars), 99.4, 99.45, 96.8, 97.0, 300))
    bars.append(_bar(len(bars), 97.0, 99.5, 96.5, 99.2, 500))
    return bars


def _liquidity_sweep_long_bars():
    bars = []
    for index in range(20):
        close = 100.0 + index * 0.06
        bars.append(_bar(index, close - 0.02, close + 0.08, close - 0.05, close, 100))
    bars.append(_bar(20, 101.2, 101.6, 99.8, 101.4, 400))
    bars.append(_bar(21, 101.4, 104.0, 101.2, 103.6, 500))
    return bars


def _liquidity_sweep_short_bars():
    bars = []
    for index in range(20):
        close = 102.0 - index * 0.06
        bars.append(_bar(index, close + 0.02, close + 0.05, close - 0.08, close, 100))
    bars.append(_bar(20, 100.8, 102.2, 100.3, 100.5, 400))
    bars.append(_bar(21, 100.5, 102.4, 100.2, 101.8, 500))
    return bars


def _mean_reversion_long_bars():
    bars = []
    for index in range(20):
        close = 99.0 if index % 2 == 0 else 101.0
        bars.append(_timed_bar(index, close - 0.05, close + 0.2, close - 0.2, close, 100))
    bars.append(_timed_bar(20, 98.7, 99.0, 97.6, 98.8, 300))
    bars.append(_timed_bar(21, 98.8, 100.2, 98.7, 100.0, 250))
    bars.append(_timed_bar(22, 100.0, 102.4, 99.5, 102.0, 250))
    return bars


def _mean_reversion_trend_day_long_bars():
    bars = []
    for index in range(20):
        close = 110.0 - index * 0.45
        bars.append(_timed_bar(index, close + 0.08, close + 0.16, close - 0.16, close, 100))
    bars.append(_timed_bar(20, 101.2, 101.8, 99.0, 101.5, 300))
    bars.append(_timed_bar(21, 101.5, 102.0, 101.0, 101.8, 250))
    return bars


def _mean_reversion_short_bars():
    bars = []
    for index in range(20):
        close = 99.0 if index % 2 == 0 else 101.0
        bars.append(_timed_bar(index, close - 0.2, close + 0.2, close - 0.2, close, 100))
    bars.append(_timed_bar(20, 101.3, 102.4, 101.0, 101.2, 300))
    bars.append(_timed_bar(21, 101.2, 101.3, 99.8, 100.0, 250))
    bars.append(_timed_bar(22, 100.0, 100.1, 97.6, 98.0, 250))
    return bars


def _momentum_context_bars(direction: str, *, start_hour: int = 11, start_minute: int = 30):
    bars = []
    for index in range(23):
        close = 100.0 + index * 0.05 if direction == "up" else 100.0 - index * 0.05
        bars.append(
            _timed_bar(
                index,
                close - 0.02,
                close + 0.08,
                close - 0.08,
                close,
                1000,
                start_hour=start_hour,
                start_minute=start_minute,
            )
        )
    return bars


def _timed_bar(index, open_price, high, low, close, volume, *, start_hour=11, start_minute=30):
    minute = start_minute + index
    hour = start_hour + minute // 60
    clock_minute = minute % 60
    return {
        "timestamp": f"2026-06-01T{hour:02d}:{clock_minute:02d}:00",
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _bar(index, open_price, high, low, close, volume):
    minute = 30 + index
    hour = 9 + minute // 60
    clock_minute = minute % 60
    return {
        "timestamp": f"2026-06-01T{hour:02d}:{clock_minute:02d}:00",
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }
