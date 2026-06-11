import json
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
    DEFAULT_RANGE_FADER_PARAMS,
    DEFAULT_RANGE_FADER_STRATEGY_ID,
    DEFAULT_TREND_RIDER_PARAMS,
    DEFAULT_TREND_RIDER_STRATEGY_ID,
    LIQUIDITY_SWEEP_TEMPLATE_KEY,
    MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY,
    RANGE_FADER_TEMPLATE_KEY,
    RANGE_FADER_TEMPLATE_VERSION,
    TREND_RIDER_TEMPLATE_KEY,
    TREND_RIDER_TEMPLATE_VERSION,
    _candidate_params_from_search_space,
    _default_optimization_search_space,
    _params_hash,
    _params_json,
    _strategy_signal_groups,
    _strategy_signal_performance,
    evaluate_bb_squeeze_breakout,
    evaluate_institutional_liquidity_sweep,
    evaluate_momentum_mean_reversion,
    evaluate_one_minute_trend_rider,
    evaluate_one_minute_range_fader,
    list_strategy_configs,
    preview_live_strategy_signal,
    run_strategy_optimization,
    run_strategy_test_batch,
    run_strategy_signal_replay,
    update_strategy_config,
)


SAMPLE_PATH = Path("tests/fixtures/stp_sample.tsv")


def test_bb_squeeze_long_entry_and_atr_target_exit():
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
        "atr_dynamic_stop",
        "atr_target_plan",
        "passive_take_profit_order",
    ]
    assert entry["metrics"]["absolute_bandwidth"] > entry["metrics"]["min_absolute_bandwidth"]
    assert entry["metrics"]["atr"] == pytest.approx(0.207857)
    assert entry["metrics"]["atr_stop_multiplier"] == 1.0
    assert entry["metrics"]["atr_target_multiplier"] == 1.5
    assert entry["stop_loss_price"] == pytest.approx(entry["price"] - entry["metrics"]["atr_stop_distance"])
    assert entry["take_profit_price"] == pytest.approx(entry["price"] + entry["metrics"]["atr_target_distance"])
    assert entry["metrics"]["atr_target_price"] == entry["take_profit_price"]
    assert entry["metrics"]["passive_take_profit_price"] == entry["take_profit_price"]
    assert entry["stop_loss_price"] < entry["price"] < entry["take_profit_price"]
    assert exit_signal["price"] == entry["take_profit_price"]
    assert exit_signal["reason_codes"] == ["atr_target", "passive_take_profit_filled"]
    assert exit_signal["linked_entry_signal_index"] == 0


def test_bb_squeeze_short_entry_and_stop_exit():
    _, signals = evaluate_bb_squeeze_breakout(_short_breakout_bars())

    assert [signal["action"] for signal in signals] == ["ENTRY_SHORT", "EXIT_SHORT"]
    entry, exit_signal = signals
    assert entry["price"] == 97.0
    assert entry["stop_loss_price"] > entry["price"] > entry["take_profit_price"]
    assert entry["stop_loss_price"] == pytest.approx(entry["price"] + entry["metrics"]["atr_stop_distance"])
    assert entry["take_profit_price"] == pytest.approx(entry["price"] - entry["metrics"]["atr_target_distance"])
    assert "atr_dynamic_stop" in entry["reason_codes"]
    assert "atr_target_plan" in entry["reason_codes"]
    assert "passive_take_profit_order" in entry["reason_codes"]
    assert exit_signal["reason_codes"] == ["stop_loss_hit"]
    assert exit_signal["linked_entry_signal_index"] == 0


def test_bb_squeeze_rejects_breakout_when_absolute_bandwidth_is_too_small():
    _, signals = evaluate_bb_squeeze_breakout(_long_breakout_bars(), {"min_absolute_bandwidth": 5.0})

    assert signals == []


def test_bb_squeeze_holds_pullback_inside_upper_band_until_exit_buffer_breaks():
    wide_atr_params = {"atr_stop_multiplier": 10.0, "atr_target_multiplier": 10.0}
    prefix = _long_breakout_bars()[:61]
    pullback_inside_upper = [*prefix, _bar(61, 103.0, 103.2, 102.0, 102.2, 500)]
    _, pullback_signals = evaluate_bb_squeeze_breakout(pullback_inside_upper, wide_atr_params)

    assert [signal["action"] for signal in pullback_signals] == ["ENTRY_LONG"]

    buffer_break = [*pullback_inside_upper, _bar(62, 102.2, 102.3, 101.1, 101.2, 450)]
    _, buffer_signals = evaluate_bb_squeeze_breakout(buffer_break, wide_atr_params)

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
    signals = [
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
    groups = _strategy_signal_groups(signals)
    performance = _strategy_signal_performance(signals)
    custom_performance = _strategy_signal_performance(
        signals,
        params={"initial_capital": 50000.0, "entry_capital_ratio": 0.1},
    )

    assert performance["unit"] == "capital_weighted_position_pnl"
    assert performance["initial_capital"] == 100000.0
    assert performance["entry_capital_ratio"] == 0.2
    assert performance["total_pnl"] == -200.0
    assert performance["gross_profit"] == 1000.0
    assert performance["gross_loss"] == -1200.0
    assert performance["closed_group_count"] == 2
    assert performance["winning_group_count"] == 1
    assert performance["losing_group_count"] == 1
    assert performance["win_rate"] == 0.5
    assert performance["profit_factor"] == 0.833333
    assert custom_performance["total_pnl"] == -50.0
    assert custom_performance["gross_profit"] == 250.0
    assert custom_performance["gross_loss"] == -300.0
    assert [group["entry_signal_id"] for group in groups] == [
        "signal-entry-long",
        "signal-entry-short",
        "signal-open-long",
    ]
    assert groups[0]["pnl"] == 1000.0
    assert groups[0]["pnl_per_share"] == 5.0
    assert groups[0]["position_notional"] == 20000.0
    assert groups[0]["position_quantity"] == 200.0
    assert groups[0]["signal_count"] == 3
    assert groups[1]["pnl"] == -1200.0
    assert groups[1]["pnl_per_share"] == -3.0
    assert groups[1]["position_quantity"] == 400.0
    assert groups[2]["pnl"] is None
    assert groups[2]["status"] == "open"


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


def test_trend_rider_long_h2_entry_and_ema9_trailing_exit():
    bars = _trend_rider_long_bars()
    series, signals = evaluate_one_minute_trend_rider(bars)

    assert len(series) == len(bars)
    assert series[31]["always_in_trend"] == 1
    assert [signal["action"] for signal in signals] == ["ENTRY_LONG", "EXIT_LONG"]
    entry, exit_signal = signals
    assert entry["bar_index"] == 35
    assert entry["take_profit_price"] is None
    assert entry["reason_codes"] == [
        "always_in_long",
        "strong_trend_breakout",
        "vwap_above",
        "ema20_slope_up",
        "h2_pullback",
        "pullback_volume_contracting",
        "ema20_reclaim",
    ]
    assert entry["metrics"]["h1_bar_index"] == 32.0
    assert entry["metrics"]["h2_bar_index"] == 34.0
    assert entry["metrics"]["pullback_volume_ratio"] < entry["metrics"]["pullback_volume_max_ratio"]
    assert entry["stop_loss_price"] < entry["price"]
    assert exit_signal["reason_codes"] == ["ema9_trailing_exit"]
    assert exit_signal["take_profit_price"] is None
    assert exit_signal["linked_entry_signal_index"] == 0


def test_trend_rider_short_l2_entry_and_hard_stop_exit():
    bars = _trend_rider_short_bars()
    _, signals = evaluate_one_minute_trend_rider(bars)

    assert [signal["action"] for signal in signals] == ["ENTRY_SHORT", "EXIT_SHORT"]
    entry, exit_signal = signals
    assert entry["reason_codes"] == [
        "always_in_short",
        "strong_trend_breakout",
        "vwap_below",
        "ema20_slope_down",
        "l2_pullback",
        "pullback_volume_contracting",
        "ema20_reject",
    ]
    assert entry["stop_loss_price"] > entry["price"]
    assert entry["take_profit_price"] is None
    assert exit_signal["reason_codes"] == ["stop_loss_hit"]
    assert exit_signal["price"] == entry["stop_loss_price"]


def test_trend_rider_rejects_pullback_without_volume_contraction():
    bars = _trend_rider_long_bars()
    for index in (32, 33, 34):
        bars[index]["volume"] = 260

    _, signals = evaluate_one_minute_trend_rider(bars)

    assert signals == []


def test_range_fader_long_edge_reversal_enters_next_open_and_exits_in_two_targets():
    bars = _range_fader_long_bars()
    series, signals = evaluate_one_minute_range_fader(bars)

    assert len(series) == len(bars)
    assert series[45]["market_regime"] == "range"
    assert series[45]["no_trade_zone"] == 0
    assert [signal["action"] for signal in signals] == ["ENTRY_LONG", "EXIT_LONG", "EXIT_LONG"]
    entry, partial_exit, final_exit = signals
    assert entry["bar_index"] == 46
    assert entry["price"] == bars[46]["open"]
    assert entry["reason_codes"] == [
        "range_regime_confirmed",
        "ema20_flat_magnet",
        "ema20_threaded",
        "bottom_edge_test",
        "failed_breakdown",
        "lower_shadow_reversal",
        "next_bar_open_entry",
        "middle_magnet_first_target",
        "partial_take_profit_plan",
        "break_even_after_middle_target",
        "opposite_range_edge_target",
    ]
    assert entry["stop_loss_price"] < entry["price"] < entry["metrics"]["first_target_price"] < entry["take_profit_price"]
    assert entry["metrics"]["range_lower_touch_count"] >= 2
    assert entry["metrics"]["range_upper_touch_count"] >= 2
    assert partial_exit["reason_codes"] == ["middle_magnet_first_target", "partial_take_profit_filled", "break_even_stop_armed"]
    assert partial_exit["price"] == entry["metrics"]["first_target_price"]
    assert partial_exit["stop_loss_price"] == entry["price"]
    assert partial_exit["metrics"]["exit_fraction"] == entry["metrics"]["first_target_exit_fraction"]
    assert partial_exit["metrics"]["break_even_stop_armed"] == 1.0
    assert final_exit["reason_codes"] == ["opposite_range_edge_target", "remaining_take_profit_filled"]
    assert final_exit["price"] == entry["take_profit_price"]
    assert final_exit["metrics"]["exit_fraction"] == 1.0 - entry["metrics"]["first_target_exit_fraction"]
    assert final_exit["linked_entry_signal_index"] == 0


def test_range_fader_moves_stop_to_break_even_after_middle_target():
    bars = _range_fader_long_bars()
    bars[48] = _bar(48, 102.6, 102.7, 100.3, 100.45, 150)

    _, signals = evaluate_one_minute_range_fader(bars)

    assert [signal["action"] for signal in signals] == ["ENTRY_LONG", "EXIT_LONG", "EXIT_LONG"]
    entry, partial_exit, break_even_exit = signals
    assert partial_exit["reason_codes"] == ["middle_magnet_first_target", "partial_take_profit_filled", "break_even_stop_armed"]
    assert break_even_exit["reason_codes"] == ["break_even_stop_hit"]
    assert break_even_exit["price"] == entry["price"]
    assert break_even_exit["stop_loss_price"] == entry["price"]
    assert break_even_exit["metrics"]["break_even_stop_armed"] == 1.0
    assert break_even_exit["metrics"]["exit_fraction"] == 1.0 - entry["metrics"]["first_target_exit_fraction"]


def test_range_fader_short_edge_reversal_and_dead_zone_rejection():
    short_bars = _range_fader_short_bars()
    _, short_signals = evaluate_one_minute_range_fader(short_bars)

    assert [signal["action"] for signal in short_signals] == ["ENTRY_SHORT", "EXIT_SHORT", "EXIT_SHORT"]
    entry, partial_exit, final_exit = short_signals
    assert entry["bar_index"] == 46
    assert entry["price"] == short_bars[46]["open"]
    assert entry["stop_loss_price"] > entry["price"] > entry["metrics"]["first_target_price"] > entry["take_profit_price"]
    assert "failed_breakout" in entry["reason_codes"]
    assert "upper_shadow_reversal" in entry["reason_codes"]
    assert partial_exit["reason_codes"] == ["middle_magnet_first_target", "partial_take_profit_filled", "break_even_stop_armed"]
    assert partial_exit["stop_loss_price"] == entry["price"]
    assert final_exit["reason_codes"] == ["opposite_range_edge_target", "remaining_take_profit_filled"]
    assert final_exit["metrics"]["exit_fraction"] == 1.0 - entry["metrics"]["first_target_exit_fraction"]

    dead_zone_bars = _range_fader_long_bars()
    dead_zone_bars[45] = _bar(45, 102.1, 102.8, 101.9, 102.4, 160)
    _, dead_zone_signals = evaluate_one_minute_range_fader(dead_zone_bars)

    assert dead_zone_signals == []


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
        assert first["signal_groups"][0]["entry_signal_id"] == first["signals"][0]["signal_id"]
        assert first["signal_groups"][0]["pnl"] == first["signal_performance"]["total_pnl"]
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


def test_trend_rider_strategy_replay_persists_archive_and_preserves_fills(tmp_path):
    conn = connect(tmp_path / "trend_rider.db")
    try:
        initialize_database(conn)
        import_stp_txt(conn, "sample.tsv", SAMPLE_PATH.read_bytes())
        update_strategy_config(conn, DEFAULT_TREND_RIDER_STRATEGY_ID, enabled=True)
        archive = archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-01",
            source_fill_count=2,
            provider=FakeMarketDataProvider(minute_bars={"AAPL": _trend_rider_long_bars()}),
        )
        before_prices = [fill["price"] for fill in list_fills(conn, date="2026-06-01")]

        run = run_strategy_signal_replay(
            conn,
            strategy_id=DEFAULT_TREND_RIDER_STRATEGY_ID,
            trade_date="2026-06-01",
            symbol="AAPL",
        )
        repeated = run_strategy_signal_replay(
            conn,
            strategy_id=DEFAULT_TREND_RIDER_STRATEGY_ID,
            trade_date="2026-06-01",
            symbol="AAPL",
        )

        assert run["run_id"] == repeated["run_id"]
        assert run["status"] == "completed"
        assert run["source_archive_id"] == archive["archive_id"]
        assert run["bars_hash"] == archive["bars_hash"]
        assert run["indicator_engine_version"] == "strategy_indicator_engine_trend_rider_v1"
        assert run["strategy"]["template_key"] == "one_minute_trend_rider_v1"
        assert run["params"]["trend_ema_period"] == 20
        assert len(run["indicator_hash"]) == 64
        assert [signal["action"] for signal in run["signals"]] == ["ENTRY_LONG", "EXIT_LONG"]
        assert run["signals"][0]["take_profit_price"] is None
        assert run["signal_performance"]["closed_group_count"] == 1
        assert [fill["price"] for fill in list_fills(conn, date="2026-06-01")] == before_prices
    finally:
        conn.close()


def test_range_fader_strategy_replay_persists_archive_and_preserves_fills(tmp_path):
    conn = connect(tmp_path / "range_fader.db")
    try:
        initialize_database(conn)
        import_stp_txt(conn, "sample.tsv", SAMPLE_PATH.read_bytes())
        update_strategy_config(conn, DEFAULT_RANGE_FADER_STRATEGY_ID, enabled=True)
        archive = archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-01",
            source_fill_count=2,
            provider=FakeMarketDataProvider(minute_bars={"AAPL": _range_fader_long_bars()}),
        )
        before_prices = [fill["price"] for fill in list_fills(conn, date="2026-06-01")]

        run = run_strategy_signal_replay(
            conn,
            strategy_id=DEFAULT_RANGE_FADER_STRATEGY_ID,
            trade_date="2026-06-01",
            symbol="AAPL",
        )
        repeated = run_strategy_signal_replay(
            conn,
            strategy_id=DEFAULT_RANGE_FADER_STRATEGY_ID,
            trade_date="2026-06-01",
            symbol="AAPL",
        )

        assert run["run_id"] == repeated["run_id"]
        assert run["status"] == "completed"
        assert run["source_archive_id"] == archive["archive_id"]
        assert run["bars_hash"] == archive["bars_hash"]
        assert run["indicator_engine_version"] == "strategy_indicator_engine_range_fader_v2"
        assert run["strategy"]["template_key"] == "one_minute_range_fader_v1"
        assert run["params"]["range_lookback_bars"] == 45
        assert len(run["indicator_hash"]) == 64
        assert [signal["action"] for signal in run["signals"]] == ["ENTRY_LONG", "EXIT_LONG", "EXIT_LONG"]
        assert run["signal_performance"]["closed_group_count"] == 1
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
        trend_rider_template = next(template for template in templates if template["template_key"] == "one_minute_trend_rider_v1")
        range_fader_template = next(template for template in templates if template["template_key"] == "one_minute_range_fader_v1")
        strategies = client.get("/api/strategies").json()["items"]
        default_strategy = next(strategy for strategy in strategies if strategy["template_key"] == "bb_squeeze_breakout_v1")
        liquidity_strategy = next(strategy for strategy in strategies if strategy["template_key"] == "institutional_liquidity_sweep_v1")
        mean_reversion_strategy = next(strategy for strategy in strategies if strategy["template_key"] == "momentum_mean_reversion_v1")
        trend_rider_strategy = next(strategy for strategy in strategies if strategy["template_key"] == "one_minute_trend_rider_v1")
        range_fader_strategy = next(strategy for strategy in strategies if strategy["template_key"] == "one_minute_range_fader_v1")
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
            json={
                "name": "BB 副本",
                "template_key": "bb_squeeze_breakout_v1",
                "params": {"atr_stop_multiplier": 1.2, "atr_target_multiplier": 2.25},
            },
        ).json()
        created_liquidity = client.post(
            "/api/strategies",
            json={"name": "Sweep 副本", "template_key": "institutional_liquidity_sweep_v1", "params": {"local_window": 20}},
        ).json()
        created_mean_reversion = client.post(
            "/api/strategies",
            json={"name": "MR 副本", "template_key": "momentum_mean_reversion_v1", "params": {"atr_stop_multiplier": 2}},
        ).json()
        created_trend_rider = client.post(
            "/api/strategies",
            json={"name": "Trend Rider 副本", "template_key": "one_minute_trend_rider_v1", "params": {"ema_slope_min": 0.01}},
        ).json()
        created_range_fader = client.post(
            "/api/strategies",
            json={
                "name": "Range Fader 副本",
                "template_key": "one_minute_range_fader_v1",
                "params": {"range_lookback_bars": 30, "max_ema_slope": 0.02},
            },
        ).json()

    assert templates[0]["template_key"] == "bb_squeeze_breakout_v1"
    assert {template["template_key"] for template in templates} == {
        "bb_squeeze_breakout_v1",
        "institutional_liquidity_sweep_v1",
        "momentum_mean_reversion_v1",
        "one_minute_trend_rider_v1",
        "one_minute_range_fader_v1",
    }
    assert {param["key"] for param in templates[0]["param_schema"]} >= {
        "exit_ema_period",
        "min_absolute_bandwidth",
        "atr_period",
        "atr_stop_multiplier",
        "atr_target_multiplier",
    }
    assert {param["key"] for param in mean_reversion_template["param_schema"]} >= {
        "adx_period",
        "adx_trend_threshold",
        "adx_chop_threshold",
        "atr_period",
        "atr_stop_multiplier",
    }
    assert {param["key"] for param in trend_rider_template["param_schema"]} >= {
        "trend_ema_period",
        "exit_ema_period",
        "breakout_volume_multiplier",
        "pullback_volume_max_ratio",
        "setup_breakout_bars",
        "ema_slope_min",
    }
    assert {param["key"] for param in range_fader_template["param_schema"]} >= {
        "range_lookback_bars",
        "edge_zone_ratio",
        "ema_period",
        "max_ema_slope",
        "min_ema_thread_bars",
        "reversal_shadow_ratio",
        "first_target_exit_fraction",
    }
    assert range_fader_template["name"] == "PA-1min边缘狙击反转策略v1.1"
    assert default_strategy["enabled"] is False
    assert default_strategy["latest_template_version"] == templates[0]["template_version"]
    assert default_strategy["is_latest_template_version"] is True
    assert default_strategy["params"]["exit_ema_period"] == 9
    assert default_strategy["params"]["min_absolute_bandwidth"] == 2.0
    assert default_strategy["params"]["atr_period"] == 14
    assert default_strategy["params"]["atr_stop_multiplier"] == 1.0
    assert default_strategy["params"]["atr_target_multiplier"] == 1.5
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
    assert trend_rider_strategy["enabled"] is False
    assert trend_rider_strategy["params"]["trend_ema_period"] == 20
    assert trend_rider_strategy["params"]["exit_ema_period"] == 9
    assert trend_rider_strategy["params"]["pullback_volume_max_ratio"] == 0.8
    assert range_fader_strategy["name"] == "PA-1min边缘狙击反转策略v1.1"
    assert range_fader_strategy["enabled"] is False
    assert range_fader_strategy["params"]["range_lookback_bars"] == 45
    assert range_fader_strategy["params"]["edge_zone_ratio"] == 0.25
    assert range_fader_strategy["params"]["ema_period"] == 20
    assert range_fader_strategy["params"]["first_target_exit_fraction"] == 0.5
    assert disabled["status"] == "strategy_disabled"
    assert enabled["enabled"] is True
    assert missing["status"] == "missing_archive"
    assert created["enabled"] is False
    assert created["params"]["atr_stop_multiplier"] == 1.2
    assert created["params"]["atr_target_multiplier"] == 2.25
    assert "risk_reward" not in created["params"]
    assert created_liquidity["params"]["exit_type"] == "OCO_Immediate"
    assert created_mean_reversion["params"]["atr_stop_multiplier"] == 2.0
    assert created_trend_rider["params"]["ema_slope_min"] == 0.01
    assert created_range_fader["params"]["range_lookback_bars"] == 30
    assert created_range_fader["params"]["max_ema_slope"] == 0.02

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
        limited_runs = client.get("/api/strategy-runs?limit=1").json()["items"]
        run_detail = client.get(f"/api/strategy-runs/{completed['run_id']}").json()

    assert completed["status"] == "completed"
    assert completed["run_id"] == repeated["run_id"]
    assert completed["signal_count"] == 2
    assert completed["signal_performance"]["closed_group_count"] == 1
    assert completed["signal_performance"]["winning_group_count"] == 1
    assert any(run["status"] == "completed" for run in runs)
    assert len(limited_runs) == 1
    completed_summary = next(run for run in runs if run["status"] == "completed")
    assert completed_summary["details_loaded"] is False
    assert completed_summary["indicator_series_json"] == ""
    assert completed_summary["indicator_series"] == []
    assert completed_summary["signals"] == []
    assert completed_summary["indicator_point_count"] == len(_long_breakout_bars())
    assert run_detail["details_loaded"] is True
    assert len(run_detail["indicator_series"]) == len(_long_breakout_bars())
    assert [signal["action"] for signal in run_detail["signals"]] == ["ENTRY_LONG", "EXIT_LONG"]


def test_default_range_fader_strategy_name_backfills_to_current_label(tmp_path):
    conn = connect(tmp_path / "range_fader_name_backfill.db")
    try:
        initialize_database(conn)
        list_strategy_configs(conn)
        for legacy_name in ("1分钟区间边缘狙击策略", "PA-1min边缘狙击反转策略"):
            with conn:
                conn.execute(
                    "UPDATE strategy_configs SET name = ? WHERE id = ?",
                    (legacy_name, DEFAULT_RANGE_FADER_STRATEGY_ID),
                )
            strategies = list_strategy_configs(conn)
            range_fader = next(strategy for strategy in strategies if strategy["strategy_id"] == DEFAULT_RANGE_FADER_STRATEGY_ID)
            assert range_fader["name"] == "PA-1min边缘狙击反转策略v1.1"

        with conn:
            conn.execute(
                "UPDATE strategy_configs SET name = ? WHERE id = ?",
                ("用户自定义边缘策略", DEFAULT_RANGE_FADER_STRATEGY_ID),
            )
        strategies = list_strategy_configs(conn)
        range_fader = next(strategy for strategy in strategies if strategy["strategy_id"] == DEFAULT_RANGE_FADER_STRATEGY_ID)

        assert range_fader["name"] == "用户自定义边缘策略"
        assert range_fader["template_version"] == RANGE_FADER_TEMPLATE_VERSION
    finally:
        conn.close()


def test_live_strategy_signal_preview_uses_provider_bars_without_persisting_runs(tmp_path):
    conn = connect(tmp_path / "live_signal.db")
    try:
        initialize_database(conn)
        update_strategy_config(conn, DEFAULT_BB_SQUEEZE_STRATEGY_ID, enabled=True)
        provider = FakeMarketDataProvider(minute_bars={"NVDA": _long_breakout_bars()[:61]})

        result = preview_live_strategy_signal(
            conn,
            strategy_id=DEFAULT_BB_SQUEEZE_STRATEGY_ID,
            symbol="nvda",
            provider="yahoo",
            lookback_minutes=120,
            market_provider=provider,
        )

        assert result["status"] == "completed"
        assert result["symbol"] == "NVDA"
        assert result["provider"] == "yahoo"
        assert result["provider_attempt_status"] == "available"
        assert result["strategy"]["latest_template_version"] == result["strategy"]["template_version"]
        assert result["strategy"]["is_latest_template_version"] is True
        assert result["order_intent"] == "BUY"
        assert result["order_action"] == "ENTRY_LONG"
        assert result["signal"]["action"] == "ENTRY_LONG"
        assert result["signal"]["position_notional"] == 20000.0
        assert result["signal"]["position_quantity"] == pytest.approx(20000.0 / result["signal"]["price"])
        assert result["signal"]["order_quantity"] == result["signal"]["position_quantity"]
        assert "upper_band_breakout" in result["reason_codes"]
        assert result["artifact_source"] == "live_provider_minute_bars"
        assert result["parser_version"] is None
        assert result["field_mapper_version"] is None
        assert result["bars_hash"]
        assert result["indicator_hash"]
        assert result["idempotency_key"].startswith("live_signal_preview:")
        assert conn.execute("SELECT COUNT(*) FROM strategy_signal_runs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM strategy_signals").fetchone()[0] == 0
    finally:
        conn.close()


def test_live_strategy_signal_api_returns_disabled_status_and_preserves_runs(tmp_path):
    db_path = tmp_path / "live_signal_api.db"

    with TestClient(create_app(db_path)) as client:
        response = client.post(
            f"/api/strategies/{DEFAULT_BB_SQUEEZE_STRATEGY_ID}/live-signal",
            json={"symbol": "NVDA", "lookback_minutes": 120},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "strategy_disabled"
        assert payload["provider"] == "yahoo"
        assert payload["order_intent"] == "HOLD"
        assert payload["provider_attempt_status"] == "not_requested"
        assert payload["signal"] is None

    conn = connect(db_path)
    try:
        initialize_database(conn)
        assert conn.execute("SELECT COUNT(*) FROM strategy_signal_runs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM strategy_signals").fetchone()[0] == 0
    finally:
        conn.close()


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
        assert batch["params"]["initial_capital"] == 100000.0
        assert batch["params"]["entry_capital_ratio"] == 0.2
        assert batch["total_pnl"] > 100.0
        assert all(day["total_pnl"] > 50.0 for day in batch["day_results"])
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
            json={"end_date": "2026-06-05", "symbol": "AAPL", "provider": "yahoo", "window_trading_days": 2},
        ).json()
        non_available = client.post(
            f"/api/strategies/{strategy['strategy_id']}/test-runs",
            json={"end_date": "2026-06-01", "symbol": "MSFT", "provider": "yahoo", "window_trading_days": 1},
        ).json()
        listed = client.get(
            f"/api/strategy-test-runs?end_date=2026-06-05&symbol=AAPL&strategy_id={strategy['strategy_id']}"
        ).json()["items"]

    assert insufficient["status"] == "insufficient_archive_coverage"
    assert insufficient["failure_reason"] == "required_recent_2_calendar_days_found_0"
    assert insufficient["day_count"] == 0
    assert listed[0]["batch_id"] == insufficient["batch_id"]
    assert non_available["status"] == "completed"
    assert non_available["completed_day_count"] == 0
    assert non_available["day_results"][0]["status"] == "non_available_archive"
    assert non_available["day_results"][0]["failure_reason"] == "fake_provider_failed"


def test_strategy_test_batch_uses_available_archives_inside_recent_calendar_window(tmp_path):
    conn = connect(tmp_path / "strategy_test_calendar_window.db")
    try:
        initialize_database(conn)
        update_strategy_config(conn, DEFAULT_BB_SQUEEZE_STRATEGY_ID, enabled=True)
        archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-05",
            source_fill_count=0,
            provider=FakeMarketDataProvider(minute_bars={"AAPL": _long_breakout_bars()}),
        )

        batch = run_strategy_test_batch(
            conn,
            strategy_id=DEFAULT_BB_SQUEEZE_STRATEGY_ID,
            end_date="2026-06-07",
            symbol="AAPL",
            window_trading_days=3,
        )
    finally:
        conn.close()

    assert batch["status"] == "completed"
    assert batch["day_count"] == 1
    assert batch["completed_day_count"] == 1
    assert batch["coverage_ratio"] == round(1 / 3, 6)
    assert [day["trade_date"] for day in batch["day_results"]] == ["2026-06-05"]


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
        "atr_stop_multiplier": [1.0],
        "atr_target_multiplier": [1.5],
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
    assert optimization["candidates"][0]["params"]["initial_capital"] == 100000.0
    assert optimization["candidates"][0]["params"]["entry_capital_ratio"] == 0.2
    assert optimization["candidates"][0]["total_pnl"] > 100.0
    assert optimization["candidates"][0]["coverage_ratio"] == 1.0
    assert listed[0]["optimization_id"] == optimization["optimization_id"]
    assert listed[0]["candidates"] == []
    assert after_strategy["params_hash"] == before_strategy["params_hash"]


def test_range_fader_optimization_uses_current_version_and_global_symbol_scope(tmp_path):
    db_path = tmp_path / "range_fader_global_optimization.db"
    conn = connect(db_path)
    try:
        initialize_database(conn)
        update_strategy_config(conn, DEFAULT_RANGE_FADER_STRATEGY_ID, enabled=True)
        for symbol in ("AAPL", "MSFT"):
            for trade_date in ("2026-06-01", "2026-06-02"):
                archive_market_minutes(
                    conn,
                    symbol=symbol,
                    trade_date=trade_date,
                    source_fill_count=0,
                    provider=FakeMarketDataProvider(minute_bars={symbol: _range_fader_long_bars()}),
                )
    finally:
        conn.close()

    search_space = {
        "range_lookback_bars": [45],
        "max_ema_slope": [0.03],
        "min_ema_thread_bars": [8],
        "reversal_shadow_ratio": [0.45],
        "first_target_exit_fraction": [0.5],
    }
    with TestClient(create_app(db_path)) as client:
        optimization = client.post(
            f"/api/strategies/{DEFAULT_RANGE_FADER_STRATEGY_ID}/optimizations",
            json={
                "end_date": "2026-06-02",
                "symbol": "AAPL",
                "symbols": ["AAPL", "MSFT"],
                "provider": "yahoo",
                "window_trading_days": 2,
                "search_space": search_space,
            },
        ).json()
        listed_for_msft = client.get(
            f"/api/strategy-optimizations?end_date=2026-06-02&symbol=MSFT&strategy_id={DEFAULT_RANGE_FADER_STRATEGY_ID}"
        ).json()["items"]
        strategy = next(
            item
            for item in client.get("/api/strategies").json()["items"]
            if item["strategy_id"] == DEFAULT_RANGE_FADER_STRATEGY_ID
        )

    assert optimization["status"] == "completed"
    assert optimization["symbol"] == "AAPL,MSFT"
    assert optimization["symbols"] == ["AAPL", "MSFT"]
    assert optimization["is_multi_symbol"] is True
    assert optimization["template_version"] == RANGE_FADER_TEMPLATE_VERSION
    assert optimization["candidate_count"] == 1
    assert optimization["eligible_candidate_count"] == 1
    assert optimization["candidates"][0]["status"] == "eligible"
    assert optimization["candidates"][0]["coverage_ratio"] == 1.0
    assert {day["symbol"] for day in optimization["candidates"][0]["day_results"]} == {"AAPL", "MSFT"}
    assert len(optimization["candidates"][0]["day_results"]) == 4
    assert listed_for_msft[0]["optimization_id"] == optimization["optimization_id"]
    assert listed_for_msft[0]["symbols"] == ["AAPL", "MSFT"]
    assert listed_for_msft[0]["candidates"] == []
    assert strategy["template_version"] == RANGE_FADER_TEMPLATE_VERSION
    assert strategy["latest_template_version"] == RANGE_FADER_TEMPLATE_VERSION


def test_multi_symbol_optimization_surfaces_per_symbol_archive_coverage_failure(tmp_path):
    db_path = tmp_path / "range_fader_global_optimization_missing.db"
    conn = connect(db_path)
    try:
        initialize_database(conn)
        update_strategy_config(conn, DEFAULT_RANGE_FADER_STRATEGY_ID, enabled=True)
        archive_market_minutes(
            conn,
            symbol="AAPL",
            trade_date="2026-06-01",
            source_fill_count=0,
            provider=FakeMarketDataProvider(minute_bars={"AAPL": _range_fader_long_bars()}),
        )
    finally:
        conn.close()

    conn = connect(db_path)
    try:
        optimization = run_strategy_optimization(
            conn,
            strategy_id=DEFAULT_RANGE_FADER_STRATEGY_ID,
            end_date="2026-06-02",
            symbol="AAPL",
            symbols=["AAPL", "MSFT"],
            window_trading_days=2,
        )
    finally:
        conn.close()

    assert optimization["status"] == "insufficient_archive_coverage"
    assert optimization["symbol"] == "AAPL,MSFT"
    assert optimization["symbols"] == ["AAPL", "MSFT"]
    assert optimization["candidate_count"] == 0
    assert optimization["failure_reason"] == "required_recent_2_calendar_days_per_symbol_found_AAPL_1_MSFT_0"


def test_apply_optimization_candidate_updates_template_version_and_records_history(tmp_path):
    db_path = tmp_path / "strategy_candidate_apply.db"
    old_params = dict(DEFAULT_TREND_RIDER_PARAMS)
    candidate_params = {
        **DEFAULT_TREND_RIDER_PARAMS,
        "breakout_volume_multiplier": 1.75,
        "pullback_volume_max_ratio": 0.55,
        "ema_slope_min": 0.01,
        "entry_body_strength_ratio": 0.55,
    }
    old_hash = _params_hash(old_params)
    candidate_hash = _params_hash(candidate_params)
    conn = connect(db_path)
    try:
        initialize_database(conn)
        with conn:
            conn.execute(
                """
                INSERT INTO strategy_configs (
                    id, name, template_key, template_version, enabled,
                    params_json, params_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    "strategy_trend_apply",
                    "Legacy Trend Apply",
                    TREND_RIDER_TEMPLATE_KEY,
                    "one_minute_trend_rider_v1.0",
                    _params_json(old_params),
                    old_hash,
                    "2026-06-01T00:00:00Z",
                    "2026-06-01T00:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO strategy_optimization_runs (
                    id, strategy_id, provider, symbol, end_date, window_trading_days,
                    archive_scope_hash, search_space_json, search_space_hash, objective,
                    template_version, indicator_engine_version, status, candidate_count,
                    eligible_candidate_count, best_candidate_id, best_params_hash,
                    best_stability_score, idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "stratopt_apply",
                    "strategy_trend_apply",
                    "yahoo",
                    "MU",
                    "2026-06-09",
                    30,
                    "scope_hash_apply",
                    json.dumps({"breakout_volume_multiplier": [1.75]}),
                    "search_hash_apply",
                    "stable_profitability_v1",
                    "one_minute_trend_rider_v1.0",
                    "strategy_indicator_engine_trend_rider_v1",
                    "completed",
                    1,
                    1,
                    "stratcand_apply",
                    candidate_hash,
                    1.0,
                    "optimization-key-apply",
                    "2026-06-09T00:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO strategy_optimization_candidates (
                    id, optimization_run_id, rank, params_json, params_hash,
                    day_results_json, status, total_pnl, win_rate, max_drawdown,
                    closed_group_count, coverage_ratio, stability_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "stratcand_apply",
                    "stratopt_apply",
                    1,
                    _params_json(candidate_params),
                    candidate_hash,
                    "[]",
                    "eligible",
                    10.0,
                    1.0,
                    0.0,
                    1,
                    1.0,
                    1.0,
                    "2026-06-09T00:00:00Z",
                ),
            )
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        applied = client.post(
            "/api/strategies/strategy_trend_apply/optimization-candidates/stratcand_apply/apply",
            json={"change_reason": "optimization_candidate_apply"},
        ).json()
        repeated = client.post(
            "/api/strategies/strategy_trend_apply/optimization-candidates/stratcand_apply/apply",
            json={"change_reason": "optimization_candidate_apply"},
        ).json()
        history = client.get("/api/strategies/strategy_trend_apply/history").json()["items"]

    assert TREND_RIDER_TEMPLATE_VERSION == "one_minute_trend_rider_v1.1"
    assert applied["template_version"] == TREND_RIDER_TEMPLATE_VERSION
    assert repeated["template_version"] == TREND_RIDER_TEMPLATE_VERSION
    assert applied["params_hash"] == candidate_hash
    assert applied["params"]["breakout_volume_multiplier"] == 1.75
    template_history = [item for item in history if item["change_source"] == "template_backfill"]
    apply_history = [item for item in history if item["change_source"] == "optimization_candidate_apply"]
    assert len(template_history) == 1
    assert template_history[0]["previous_template_version"] == "one_minute_trend_rider_v1.0"
    assert template_history[0]["next_template_version"] == "one_minute_trend_rider_v1.1"
    assert template_history[0]["change_reason"] == "template_registry_upgrade"
    assert len(apply_history) == 1
    assert apply_history[0]["optimization_run_id"] == "stratopt_apply"
    assert apply_history[0]["candidate_id"] == "stratcand_apply"
    assert apply_history[0]["next_template_version"] == "one_minute_trend_rider_v1.1"
    assert apply_history[0]["next_params_hash"] == candidate_hash
    assert apply_history[0]["change_reason"] == "optimization_candidate_apply"


def test_strategy_config_history_rollback_restores_previous_params_and_records_history(tmp_path):
    db_path = tmp_path / "strategy_history_rollback.db"
    with TestClient(create_app(db_path)) as client:
        strategy = next(
            item
            for item in client.get("/api/strategies").json()["items"]
            if item["strategy_id"] == DEFAULT_BB_SQUEEZE_STRATEGY_ID
        )
        original_hash = strategy["params_hash"]
        original_rsi_period = strategy["params"]["rsi_period"]
        edited_params = {**strategy["params"], "rsi_period": original_rsi_period + 2}
        edited = client.patch(
            f"/api/strategies/{strategy['strategy_id']}",
            json={"params": edited_params},
        ).json()
        history = client.get(f"/api/strategies/{strategy['strategy_id']}/history").json()["items"]
        manual_history = [item for item in history if item["change_source"] == "manual_edit"]

        assert len(manual_history) == 1
        assert manual_history[0]["previous_params_hash"] == original_hash
        assert manual_history[0]["next_params_hash"] == edited["params_hash"]
        assert manual_history[0]["previous_params"]["rsi_period"] == original_rsi_period
        assert manual_history[0]["next_params"]["rsi_period"] == original_rsi_period + 2
        assert manual_history[0]["can_rollback"] is True

        rollback = client.post(
            f"/api/strategies/{strategy['strategy_id']}/history/{manual_history[0]['history_id']}/rollback",
            json={"change_reason": "history_rollback"},
        ).json()
        repeat = client.post(
            f"/api/strategies/{strategy['strategy_id']}/history/{manual_history[0]['history_id']}/rollback",
            json={"change_reason": "history_rollback"},
        )
        after_history = client.get(f"/api/strategies/{strategy['strategy_id']}/history").json()["items"]
        rollback_history = [item for item in after_history if item["change_source"] == "history_rollback"]

    assert rollback["params_hash"] == original_hash
    assert rollback["params"]["rsi_period"] == original_rsi_period
    assert repeat.status_code == 422
    assert repeat.json()["detail"] == "strategy_config_history_already_current"
    assert len(rollback_history) == 1
    assert rollback_history[0]["source_history_id"] == manual_history[0]["history_id"]
    assert rollback_history[0]["previous_params_hash"] == edited["params_hash"]
    assert rollback_history[0]["next_params_hash"] == original_hash
    assert rollback_history[0]["previous_params"]["rsi_period"] == original_rsi_period + 2
    assert rollback_history[0]["next_params"]["rsi_period"] == original_rsi_period


def test_strategy_config_history_rollback_preserves_historical_template_version_after_list_backfill(tmp_path):
    db_path = tmp_path / "strategy_history_rollback_template_version.db"
    params = dict(DEFAULT_BB_SQUEEZE_PARAMS)
    params_json = _params_json(params)
    params_hash = _params_hash(params)
    conn = connect(db_path)
    try:
        initialize_database(conn)
        with conn:
            conn.execute(
                """
                INSERT INTO strategy_configs (
                    id, name, template_key, template_version, enabled,
                    params_json, params_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    "strategy_bb_history_version",
                    "History Version BB",
                    BB_SQUEEZE_TEMPLATE_KEY,
                    "bb_squeeze_breakout_v1.2",
                    params_json,
                    params_hash,
                    "2026-06-09T00:00:00Z",
                    "2026-06-09T00:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO strategy_config_history (
                    id, strategy_id, change_source, previous_template_version,
                    next_template_version, previous_params_hash, next_params_hash,
                    previous_params_json, next_params_json, change_reason,
                    optimization_run_id, candidate_id, source_history_id,
                    idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "stratchg_bb_template_upgrade",
                    "strategy_bb_history_version",
                    "template_backfill",
                    "bb_squeeze_breakout_v1.1",
                    "bb_squeeze_breakout_v1.2",
                    params_hash,
                    params_hash,
                    params_json,
                    params_json,
                    "template_registry_upgrade",
                    None,
                    None,
                    None,
                    "bb-template-upgrade-key",
                    "2026-06-09T00:00:01Z",
                ),
            )
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        rollback = client.post(
            "/api/strategies/strategy_bb_history_version/history/stratchg_bb_template_upgrade/rollback",
            json={"change_reason": "history_rollback"},
        ).json()
        listed = next(
            item
            for item in client.get("/api/strategies").json()["items"]
            if item["strategy_id"] == "strategy_bb_history_version"
        )
        repeat = client.post(
            "/api/strategies/strategy_bb_history_version/history/stratchg_bb_template_upgrade/rollback",
            json={"change_reason": "history_rollback"},
        )
        history = client.get("/api/strategies/strategy_bb_history_version/history").json()["items"]
        rollback_history = [item for item in history if item["change_source"] == "history_rollback"]

    assert rollback["template_version"] == "bb_squeeze_breakout_v1.1"
    assert listed["template_version"] == "bb_squeeze_breakout_v1.1"
    assert repeat.status_code == 422
    assert repeat.json()["detail"] == "strategy_config_history_already_current"
    assert len(rollback_history) == 1
    assert rollback_history[0]["previous_template_version"] == "bb_squeeze_breakout_v1.2"
    assert rollback_history[0]["next_template_version"] == "bb_squeeze_breakout_v1.1"
    assert rollback_history[0]["source_history_id"] == "stratchg_bb_template_upgrade"


def test_apply_range_fader_candidate_updates_template_version_and_records_history(tmp_path):
    db_path = tmp_path / "range_fader_candidate_apply.db"
    old_params = dict(DEFAULT_RANGE_FADER_PARAMS)
    candidate_params = {
        **DEFAULT_RANGE_FADER_PARAMS,
        "range_lookback_bars": 60,
        "max_ema_slope": 0.05,
        "min_ema_thread_bars": 12,
        "reversal_shadow_ratio": 0.55,
    }
    old_hash = _params_hash(old_params)
    candidate_hash = _params_hash(candidate_params)
    conn = connect(db_path)
    try:
        initialize_database(conn)
        with conn:
            conn.execute(
                """
                INSERT INTO strategy_configs (
                    id, name, template_key, template_version, enabled,
                    params_json, params_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    "strategy_range_apply",
                    "Legacy Range Apply",
                    RANGE_FADER_TEMPLATE_KEY,
                    "one_minute_range_fader_v1.0",
                    _params_json(old_params),
                    old_hash,
                    "2026-06-01T00:00:00Z",
                    "2026-06-01T00:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO strategy_optimization_runs (
                    id, strategy_id, provider, symbol, end_date, window_trading_days,
                    archive_scope_hash, search_space_json, search_space_hash, objective,
                    template_version, indicator_engine_version, status, candidate_count,
                    eligible_candidate_count, best_candidate_id, best_params_hash,
                    best_stability_score, idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "stratopt_range_apply",
                    "strategy_range_apply",
                    "yahoo",
                    "TSLA",
                    "2026-06-09",
                    30,
                    "scope_hash_range_apply",
                    json.dumps({"range_lookback_bars": [60]}),
                    "search_hash_range_apply",
                    "stable_profitability_v1",
                    "one_minute_range_fader_v1.0",
                    "strategy_indicator_engine_range_fader_v2",
                    "completed",
                    1,
                    1,
                    "stratcand_range_apply",
                    candidate_hash,
                    1.0,
                    "optimization-key-range-apply",
                    "2026-06-09T00:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO strategy_optimization_candidates (
                    id, optimization_run_id, rank, params_json, params_hash,
                    day_results_json, status, total_pnl, win_rate, max_drawdown,
                    closed_group_count, coverage_ratio, stability_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "stratcand_range_apply",
                    "stratopt_range_apply",
                    1,
                    _params_json(candidate_params),
                    candidate_hash,
                    "[]",
                    "eligible",
                    12.0,
                    1.0,
                    0.0,
                    1,
                    1.0,
                    1.0,
                    "2026-06-09T00:00:00Z",
                ),
            )
    finally:
        conn.close()

    with TestClient(create_app(db_path)) as client:
        applied = client.post(
            "/api/strategies/strategy_range_apply/optimization-candidates/stratcand_range_apply/apply",
            json={"change_reason": "optimization_candidate_apply"},
        ).json()
        repeated = client.post(
            "/api/strategies/strategy_range_apply/optimization-candidates/stratcand_range_apply/apply",
            json={"change_reason": "optimization_candidate_apply"},
        ).json()
        history = client.get("/api/strategies/strategy_range_apply/history").json()["items"]

    assert RANGE_FADER_TEMPLATE_VERSION == "one_minute_range_fader_v1.1"
    assert applied["template_version"] == RANGE_FADER_TEMPLATE_VERSION
    assert repeated["template_version"] == RANGE_FADER_TEMPLATE_VERSION
    assert applied["params_hash"] == candidate_hash
    assert applied["params"]["range_lookback_bars"] == 60
    template_history = [item for item in history if item["change_source"] == "template_backfill"]
    apply_history = [item for item in history if item["change_source"] == "optimization_candidate_apply"]
    assert len(template_history) == 1
    assert template_history[0]["previous_template_version"] == "one_minute_range_fader_v1.0"
    assert template_history[0]["next_template_version"] == "one_minute_range_fader_v1.1"
    assert template_history[0]["change_reason"] == "template_registry_upgrade"
    assert len(apply_history) == 1
    assert apply_history[0]["optimization_run_id"] == "stratopt_range_apply"
    assert apply_history[0]["candidate_id"] == "stratcand_range_apply"
    assert apply_history[0]["next_template_version"] == "one_minute_range_fader_v1.1"
    assert apply_history[0]["next_params_hash"] == candidate_hash
    assert apply_history[0]["change_reason"] == "optimization_candidate_apply"


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
                    "atr_stop_multiplier": [0.8, 1.0, 1.2, 1.5],
                    "atr_target_multiplier": [1.0, 1.5, 2.0, 2.5],
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
            {
                "volume_multiplier",
                "squeeze_percentile",
                "atr_stop_multiplier",
                "atr_target_multiplier",
                "min_absolute_bandwidth",
                "setup_minutes",
            },
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
        (
            TREND_RIDER_TEMPLATE_KEY,
            DEFAULT_TREND_RIDER_PARAMS,
            {
                "breakout_volume_multiplier",
                "pullback_volume_max_ratio",
                "ema_slope_min",
                "big_body_strength_ratio",
                "entry_body_strength_ratio",
            },
        ),
        (
            RANGE_FADER_TEMPLATE_KEY,
            DEFAULT_RANGE_FADER_PARAMS,
            {
                "range_lookback_bars",
                "max_ema_slope",
                "min_ema_thread_bars",
                "reversal_shadow_ratio",
                "first_target_exit_fraction",
            },
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
    assert payload["failure_reason"] == "required_recent_30_calendar_days_found_0"


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

        assert strategy["template_version"] == "bb_squeeze_breakout_v1.2"
        assert strategy["params"]["exit_ema_period"] == 9
        assert strategy["params"]["min_absolute_bandwidth"] == 2.0
        assert strategy["params"]["atr_period"] == 14
        assert strategy["params"]["atr_stop_multiplier"] == 1.0
        assert strategy["params"]["atr_target_multiplier"] == 1.5
        assert strategy["params"]["initial_capital"] == 100000.0
        assert strategy["params"]["entry_capital_ratio"] == 0.2
        assert "risk_reward" not in strategy["params"]
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
        assert strategy["params"]["initial_capital"] == 100000.0
        assert strategy["params"]["entry_capital_ratio"] == 0.2
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


def _range_fader_base_bars():
    bars = []
    for index in range(45):
        close = 101.8 if index % 2 == 0 else 103.2
        bars.append(_bar(index, close - 0.2, 105.0, 100.0, close, 100))
    return bars


def _range_fader_long_bars():
    bars = _range_fader_base_bars()
    bars.append(_bar(45, 100.2, 100.55, 99.7, 100.4, 160))
    bars.append(_bar(46, 100.45, 101.8, 100.35, 101.6, 140))
    bars.append(_bar(47, 101.6, 102.9, 101.5, 102.6, 150))
    bars.append(_bar(48, 102.6, 105.2, 102.5, 104.9, 150))
    bars.append(_bar(49, 104.9, 105.3, 103.0, 103.1, 180))
    return bars


def _range_fader_short_bars():
    bars = _range_fader_base_bars()
    bars.append(_bar(45, 104.8, 105.3, 104.45, 104.6, 160))
    bars.append(_bar(46, 104.55, 104.65, 103.2, 103.4, 140))
    bars.append(_bar(47, 103.4, 103.5, 102.0, 102.3, 150))
    bars.append(_bar(48, 102.3, 102.4, 99.8, 100.1, 150))
    bars.append(_bar(49, 100.1, 102.0, 99.7, 101.9, 180))
    return bars


def _trend_rider_long_bars():
    bars = []
    for index in range(30):
        close = 100.0 if index % 2 == 0 else 100.2
        bars.append(_bar(index, close - 0.05, close + 0.2, close - 0.2, close, 100))
    bars.append(_bar(30, 100.2, 102.1, 100.15, 101.9, 260))
    bars.append(_bar(31, 101.9, 104.4, 101.85, 104.2, 270))
    bars.append(_bar(32, 104.2, 104.3, 100.7, 102.0, 80))
    bars.append(_bar(33, 102.0, 103.0, 101.4, 102.8, 70))
    bars.append(_bar(34, 102.8, 103.0, 100.9, 102.2, 70))
    bars.append(_bar(35, 102.2, 103.4, 102.1, 103.2, 120))
    bars.append(_bar(36, 103.2, 104.0, 103.0, 103.8, 120))
    bars.append(_bar(37, 103.8, 104.2, 102.8, 103.1, 120))
    bars.append(_bar(38, 103.1, 103.2, 101.8, 102.0, 120))
    return bars


def _trend_rider_short_bars():
    bars = []
    for index in range(30):
        close = 100.2 if index % 2 == 0 else 100.0
        bars.append(_bar(index, close - 0.2, close + 0.2, close - 0.05, close, 100))
    bars.append(_bar(30, 99.8, 99.85, 97.9, 98.1, 260))
    bars.append(_bar(31, 98.1, 98.15, 95.8, 96.0, 270))
    bars.append(_bar(32, 96.0, 99.4, 95.9, 98.0, 80))
    bars.append(_bar(33, 98.0, 98.4, 97.2, 97.4, 70))
    bars.append(_bar(34, 97.4, 99.3, 97.3, 98.2, 70))
    bars.append(_bar(35, 98.2, 98.3, 97.0, 97.1, 120))
    bars.append(_bar(36, 97.1, 99.6, 96.8, 99.0, 120))
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
