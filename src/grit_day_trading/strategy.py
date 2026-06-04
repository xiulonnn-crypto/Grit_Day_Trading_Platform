from __future__ import annotations

import hashlib
import itertools
import json
import math
import sqlite3
from datetime import UTC, datetime
from typing import Any

from .storage import dumps_json, new_id, row_to_dict, rows_to_dicts


BB_SQUEEZE_TEMPLATE_KEY = "bb_squeeze_breakout_v1"
BB_SQUEEZE_TEMPLATE_VERSION = "bb_squeeze_breakout_v1.1"
BB_SQUEEZE_ENGINE_VERSION = "strategy_indicator_engine_v2"
DEFAULT_BB_SQUEEZE_STRATEGY_ID = "strategy_bb_squeeze_default"
LIQUIDITY_SWEEP_TEMPLATE_KEY = "institutional_liquidity_sweep_v1"
LIQUIDITY_SWEEP_TEMPLATE_VERSION = "institutional_liquidity_sweep_v1.0"
LIQUIDITY_SWEEP_ENGINE_VERSION = "strategy_indicator_engine_liquidity_sweep_v1"
DEFAULT_LIQUIDITY_SWEEP_STRATEGY_ID = "strategy_liquidity_sweep_default"
MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY = "momentum_mean_reversion_v1"
MOMENTUM_MEAN_REVERSION_TEMPLATE_VERSION = "momentum_mean_reversion_v1.1"
MOMENTUM_MEAN_REVERSION_ENGINE_VERSION = "strategy_indicator_engine_momentum_mean_reversion_v2"
DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID = "strategy_momentum_mean_reversion_default"
MOMENTUM_CONTEXT_SYMBOLS = ("QQQ", "SMH")

DEFAULT_BB_SQUEEZE_PARAMS: dict[str, float | int] = {
    "bb_period": 20,
    "bb_stddev": 2.0,
    "rsi_period": 14,
    "volume_average_period": 20,
    "volume_multiplier": 2.0,
    "squeeze_percentile": 10.0,
    "setup_minutes": 10,
    "body_strength_ratio": 0.5,
    "risk_reward": 2.0,
    "exit_ema_period": 9,
    "min_absolute_bandwidth": 2.0,
}

DEFAULT_LIQUIDITY_SWEEP_PARAMS: dict[str, float | int | str] = {
    "local_window": 20,
    "shadow_ratio": 0.6,
    "volume_average_period": 20,
    "volume_multiplier": 1.5,
    "bb_period": 20,
    "bb_stddev": 2.0,
    "risk_reward": 1.5,
    "tick_size": 0.01,
    "stop_tick_offset": 2,
    "max_holding_bars": 3,
    "exit_type": "OCO_Immediate",
}

DEFAULT_MOMENTUM_MEAN_REVERSION_PARAMS: dict[str, float | int | str] = {
    "bb_period": 20,
    "bb_stddev": 2.0,
    "adx_period": 14,
    "adx_trend_threshold": 25.0,
    "adx_chop_threshold": 20.0,
    "atr_period": 14,
    "atr_stop_multiplier": 1.5,
    "start_hour": 11,
    "start_minute": 30,
    "end_hour": 13,
    "end_minute": 30,
    "pin_shadow_ratio": 0.55,
    "swing_lookback": 3,
    "tick_size": 0.01,
    "first_target_exit_fraction": 0.5,
    "momentum_context": "QQQ_SMH",
}

RUN_STATUSES = {
    "completed",
    "missing_archive",
    "non_available_archive",
    "insufficient_bars",
    "strategy_disabled",
    "failed",
}

STRATEGY_TEST_BATCH_STATUSES = {
    "completed",
    "insufficient_archive_coverage",
    "strategy_disabled",
    "failed",
}
STRATEGY_OPTIMIZATION_STATUSES = set(STRATEGY_TEST_BATCH_STATUSES)
STRATEGY_OPTIMIZATION_CANDIDATE_STATUSES = {
    "eligible",
    "no_signals",
    "failed",
    "insufficient_archive_coverage",
    "strategy_disabled",
}
DEFAULT_STRATEGY_TEST_WINDOW_DAYS = 30
MAX_OPTIMIZATION_CANDIDATES = 120
DEFAULT_OPTIMIZATION_OBJECTIVE = "stable_profitability_v1"


def get_strategy_templates() -> list[dict[str, Any]]:
    return [
        {
            "template_key": BB_SQUEEZE_TEMPLATE_KEY,
            "template_version": BB_SQUEEZE_TEMPLATE_VERSION,
            "name": "1分钟布林带收缩突破策略",
            "description": "捕捉波动率从极小向极大转换的 1 分钟 BB Squeeze Breakout 复盘信号。",
            "default_params": dict(DEFAULT_BB_SQUEEZE_PARAMS),
            "param_schema": [
                {"key": "bb_period", "label": "布林带周期", "type": "integer", "min": 5, "max": 100},
                {"key": "bb_stddev", "label": "布林带标准差", "type": "number", "min": 0.5, "max": 5.0},
                {"key": "rsi_period", "label": "RSI 周期", "type": "integer", "min": 2, "max": 100},
                {"key": "volume_average_period", "label": "均量周期", "type": "integer", "min": 2, "max": 100},
                {"key": "volume_multiplier", "label": "量能倍数", "type": "number", "min": 1.0, "max": 10.0},
                {"key": "squeeze_percentile", "label": "收缩分位数", "type": "number", "min": 1.0, "max": 50.0},
                {"key": "setup_minutes", "label": "横盘分钟数", "type": "integer", "min": 3, "max": 60},
                {"key": "body_strength_ratio", "label": "实体强度", "type": "number", "min": 0.1, "max": 1.0},
                {"key": "risk_reward", "label": "盈亏比目标", "type": "number", "min": 0.5, "max": 10.0},
                {"key": "exit_ema_period", "label": "出场 EMA 周期", "type": "integer", "min": 2, "max": 60},
                {"key": "min_absolute_bandwidth", "label": "最小绝对带宽", "type": "number", "min": 0.0, "max": 100.0},
            ],
        },
        {
            "template_key": LIQUIDITY_SWEEP_TEMPLATE_KEY,
            "template_version": LIQUIDITY_SWEEP_TEMPLATE_VERSION,
            "name": "1分钟机构流动性掠夺策略",
            "description": "捕捉前一局部高低点被扫穿后迅速收回的 1 分钟 Liquidity Sweep 复盘信号。",
            "default_params": dict(DEFAULT_LIQUIDITY_SWEEP_PARAMS),
            "param_schema": [
                {"key": "local_window", "label": "局部窗口", "type": "integer", "min": 10, "max": 60},
                {"key": "shadow_ratio", "label": "影线占比", "type": "number", "min": 0.2, "max": 0.95},
                {"key": "volume_average_period", "label": "均量周期", "type": "integer", "min": 2, "max": 100},
                {"key": "volume_multiplier", "label": "放量倍数", "type": "number", "min": 1.0, "max": 10.0},
                {"key": "bb_period", "label": "布林中轨周期", "type": "integer", "min": 5, "max": 100},
                {"key": "bb_stddev", "label": "布林标准差", "type": "number", "min": 0.5, "max": 5.0},
                {"key": "risk_reward", "label": "盈亏比目标", "type": "number", "min": 0.5, "max": 10.0},
                {"key": "tick_size", "label": "Tick 大小", "type": "number", "min": 0.0001, "max": 1.0},
                {"key": "stop_tick_offset", "label": "止损 Tick", "type": "integer", "min": 1, "max": 5},
                {"key": "max_holding_bars", "label": "最长持仓 K 数", "type": "integer", "min": 1, "max": 10},
                {
                    "key": "exit_type",
                    "label": "出场模式",
                    "type": "enum",
                    "options": [{"value": "OCO_Immediate", "label": "OCO_Immediate"}],
                },
            ],
        },
        {
            "template_key": MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY,
            "template_version": MOMENTUM_MEAN_REVERSION_TEMPLATE_VERSION,
            "name": "1分钟动能过滤均值回归策略",
            "description": "在 QQQ 与 SMH 同向 VWAP、ADX 震荡 regime 和 ATR 动态止损约束下，只在 11:30-13:30 捕捉 1 分钟布林带反转均值回归信号。",
            "default_params": dict(DEFAULT_MOMENTUM_MEAN_REVERSION_PARAMS),
            "param_schema": [
                {"key": "bb_period", "label": "布林带周期", "type": "integer", "min": 5, "max": 100},
                {"key": "bb_stddev", "label": "布林带标准差", "type": "number", "min": 0.5, "max": 5.0},
                {"key": "adx_period", "label": "ADX 周期", "type": "integer", "min": 2, "max": 60},
                {"key": "adx_trend_threshold", "label": "ADX 趋势熔断阈值", "type": "number", "min": 5.0, "max": 80.0},
                {"key": "adx_chop_threshold", "label": "ADX 震荡激活阈值", "type": "number", "min": 1.0, "max": 60.0},
                {"key": "atr_period", "label": "ATR 周期", "type": "integer", "min": 2, "max": 60},
                {"key": "atr_stop_multiplier", "label": "ATR 止损倍数", "type": "number", "min": 0.1, "max": 10.0},
                {"key": "start_hour", "label": "开始小时 ET", "type": "integer", "min": 0, "max": 23},
                {"key": "start_minute", "label": "开始分钟", "type": "integer", "min": 0, "max": 59},
                {"key": "end_hour", "label": "结束小时 ET", "type": "integer", "min": 0, "max": 23},
                {"key": "end_minute", "label": "结束分钟", "type": "integer", "min": 0, "max": 59},
                {"key": "pin_shadow_ratio", "label": "Pin Bar 影线占比", "type": "number", "min": 0.2, "max": 0.95},
                {"key": "swing_lookback", "label": "近期波谷窗口", "type": "integer", "min": 1, "max": 20},
                {"key": "tick_size", "label": "Tick 大小", "type": "number", "min": 0.0001, "max": 1.0},
                {"key": "first_target_exit_fraction", "label": "中轨平仓比例", "type": "number", "min": 0.5, "max": 0.75},
                {
                    "key": "momentum_context",
                    "label": "动能过滤来源",
                    "type": "enum",
                    "options": [{"value": "QQQ_SMH", "label": "QQQ + SMH"}],
                },
            ],
        },
    ]


def ensure_default_strategy_configs(conn: sqlite3.Connection) -> None:
    now = _now()
    with conn:
        for template in get_strategy_templates():
            template_key = template["template_key"]
            default_id = _default_strategy_id(template_key)
            params = _normalize_params(template["default_params"], template_key=template_key)
            conn.execute(
                """
                INSERT OR IGNORE INTO strategy_configs (
                    id, name, template_key, template_version, enabled,
                    params_json, params_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)
                """,
                (
                    default_id,
                    template["name"],
                    template_key,
                    template["template_version"],
                    _params_json(params),
                    _params_hash(params),
                    now,
                    now,
                ),
            )
            rows = conn.execute(
                """
                SELECT id, template_version, params_json, params_hash
                FROM strategy_configs
                WHERE template_key = ?
                """,
                (template_key,),
            ).fetchall()
            for row in rows:
                normalized = _normalize_params(json.loads(row["params_json"]), template_key=template_key)
                params_json = _params_json(normalized)
                params_hash = _params_hash(normalized)
                if (
                    row["template_version"] != template["template_version"]
                    or row["params_json"] != params_json
                    or row["params_hash"] != params_hash
                ):
                    conn.execute(
                        """
                        UPDATE strategy_configs
                        SET template_version = ?, params_json = ?, params_hash = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (template["template_version"], params_json, params_hash, now, row["id"]),
                    )


def _default_strategy_id(template_key: str) -> str:
    if template_key == BB_SQUEEZE_TEMPLATE_KEY:
        return DEFAULT_BB_SQUEEZE_STRATEGY_ID
    if template_key == LIQUIDITY_SWEEP_TEMPLATE_KEY:
        return DEFAULT_LIQUIDITY_SWEEP_STRATEGY_ID
    if template_key == MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY:
        return DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID
    raise ValueError("unsupported_strategy_template")


def list_strategy_configs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_default_strategy_configs(conn)
    rows = conn.execute(
        """
        SELECT * FROM strategy_configs
        ORDER BY enabled DESC, updated_at DESC, created_at DESC, name
        """
    ).fetchall()
    return [_public_strategy_config(row) for row in rows]


def create_strategy_config(
    conn: sqlite3.Connection,
    *,
    name: str,
    template_key: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    template = _template_for_key(template_key)
    normalized_params = _normalize_params(params or template["default_params"], template_key=template["template_key"])
    config_id = new_id("strategy")
    now = _now()
    with conn:
        conn.execute(
            """
            INSERT INTO strategy_configs (
                id, name, template_key, template_version, enabled,
                params_json, params_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                config_id,
                _clean_name(name),
                template["template_key"],
                template["template_version"],
                _params_json(normalized_params),
                _params_hash(normalized_params),
                now,
                now,
            ),
        )
    return get_strategy_config(conn, config_id)


def update_strategy_config(
    conn: sqlite3.Connection,
    strategy_id: str,
    *,
    name: str | None = None,
    enabled: bool | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = _strategy_config_row(conn, strategy_id)
    current_params = json.loads(existing["params_json"])
    next_params = _normalize_params(current_params if params is None else params, template_key=existing["template_key"])
    next_name = _clean_name(existing["name"] if name is None else name)
    next_enabled = int(bool(existing["enabled"] if enabled is None else enabled))
    with conn:
        conn.execute(
            """
            UPDATE strategy_configs
            SET name = ?, enabled = ?, params_json = ?, params_hash = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                next_name,
                next_enabled,
                _params_json(next_params),
                _params_hash(next_params),
                _now(),
                strategy_id,
            ),
        )
    return get_strategy_config(conn, strategy_id)


def get_strategy_config(conn: sqlite3.Connection, strategy_id: str) -> dict[str, Any]:
    return _public_strategy_config(_strategy_config_row(conn, strategy_id))


def run_strategy_signal_replay(
    conn: sqlite3.Connection,
    *,
    strategy_id: str,
    trade_date: str,
    symbol: str,
    provider: str = "yahoo",
    force: bool = False,
) -> dict[str, Any]:
    ensure_default_strategy_configs(conn)
    config_row = _strategy_config_row(conn, strategy_id)
    config = _public_strategy_config(config_row)
    params = _normalize_params(config["params"], template_key=config["template_key"])
    return _run_strategy_signal_replay_with_params(
        conn,
        strategy_id=strategy_id,
        trade_date=trade_date,
        symbol=symbol,
        provider=provider,
        params=params,
        params_hash=config["params_hash"],
        template_key=config["template_key"],
        template_version=config["template_version"],
        enabled=config["enabled"],
        force=force,
    )


def _run_strategy_signal_replay_with_params(
    conn: sqlite3.Connection,
    *,
    strategy_id: str,
    trade_date: str,
    symbol: str,
    provider: str,
    params: dict[str, Any],
    params_hash: str,
    template_key: str,
    template_version: str,
    enabled: bool,
    force: bool = False,
) -> dict[str, Any]:
    provider_key = provider.strip().lower() or "yahoo"
    canonical_symbol = symbol.strip().upper()
    indicator_engine_version = _engine_version_for_template(template_key)

    archive = _find_archive(conn, provider=provider_key, symbol=canonical_symbol, trade_date=trade_date)
    context_archives = _find_strategy_context_archives(
        conn,
        template_key=template_key,
        params=params,
        provider=provider_key,
        trade_date=trade_date,
    )
    missing_context_symbols = _missing_context_symbols(template_key, params, context_archives)
    non_available_context = _non_available_context_archives(context_archives)
    source_archive_id = archive["id"] if archive else None
    bars_hash = _strategy_input_bars_hash(
        template_key=template_key,
        primary_archive=archive,
        context_archives=context_archives,
        params=params,
    )
    idempotency_key = _run_idempotency_key(
        strategy_id=strategy_id,
        provider=provider_key,
        symbol=canonical_symbol,
        trade_date=trade_date,
        source_archive_id=source_archive_id,
        bars_hash=bars_hash,
        params_hash=params_hash,
        template_version=template_version,
        indicator_engine_version=indicator_engine_version,
    )
    existing = _find_run_by_key(conn, idempotency_key)

    status = "completed"
    failure_reason: str | None = None
    indicator_series: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []

    if not enabled:
        status = "strategy_disabled"
        failure_reason = "strategy_disabled"
    elif archive is None:
        status = "missing_archive"
        failure_reason = "minute_archive_required"
    elif archive["data_status"] != "available":
        status = "non_available_archive"
        failure_reason = archive["failure_reason"] or archive["data_status"]
    elif missing_context_symbols:
        status = "missing_archive"
        failure_reason = f"momentum_context_archive_required:{','.join(missing_context_symbols)}"
    elif non_available_context:
        status = "non_available_archive"
        failure_reason = "momentum_context_archive_unavailable:" + ",".join(
            f"{symbol}:{row['data_status']}" for symbol, row in non_available_context.items()
        )
    else:
        bars = json.loads(archive["bars_json"])
        if len(bars) < _minimum_required_bars(params, template_key=template_key):
            status = "insufficient_bars"
            failure_reason = "insufficient_minute_bars"
        else:
            try:
                indicator_series, signals = _evaluate_strategy(
                    template_key,
                    bars,
                    params,
                    context_bars=_context_bars_for_template(template_key, context_archives),
                )
            except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                status = "failed"
                failure_reason = f"strategy_engine_failed:{exc.__class__.__name__}"

    if existing and not force and existing["status"] == status:
        return get_strategy_signal_run(conn, existing["id"])

    return _store_strategy_run(
        conn,
        existing_run_id=existing["id"] if existing else None,
        strategy_id=strategy_id,
        provider=provider_key,
        symbol=canonical_symbol,
        trade_date=trade_date,
        source_archive_id=source_archive_id,
        bars_hash=bars_hash,
        params_hash=params_hash,
        params_json=_params_json(params),
        status=status,
        failure_reason=failure_reason,
        indicator_series=indicator_series,
        signals=signals,
        idempotency_key=idempotency_key,
        indicator_engine_version=indicator_engine_version,
    )


def list_strategy_signal_runs(
    conn: sqlite3.Connection,
    *,
    trade_date: str | None = None,
    symbol: str | None = None,
    strategy_id: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if trade_date:
        clauses.append("r.trade_date = ?")
        params.append(trade_date)
    if symbol:
        clauses.append("r.symbol = ?")
        params.append(symbol.strip().upper())
    if strategy_id:
        clauses.append("r.strategy_id = ?")
        params.append(strategy_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT r.*, c.name AS strategy_name, c.template_key, c.template_version,
            c.params_json AS strategy_config_params_json
        FROM strategy_signal_runs r
        JOIN strategy_configs c ON c.id = r.strategy_id
        {where}
        ORDER BY r.created_at DESC, r.id DESC
        """,
        params,
    ).fetchall()
    return [_public_strategy_run(conn, row) for row in rows]


def get_strategy_signal_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT r.*, c.name AS strategy_name, c.template_key, c.template_version,
            c.params_json AS strategy_config_params_json
        FROM strategy_signal_runs r
        JOIN strategy_configs c ON c.id = r.strategy_id
        WHERE r.id = ?
        """,
        (run_id,),
    ).fetchone()
    if not row:
        raise KeyError("strategy_signal_run_not_found")
    return _public_strategy_run(conn, row)


def run_strategy_test_batch(
    conn: sqlite3.Connection,
    *,
    strategy_id: str,
    end_date: str,
    symbol: str,
    provider: str = "yahoo",
    window_trading_days: int = DEFAULT_STRATEGY_TEST_WINDOW_DAYS,
    force: bool = False,
) -> dict[str, Any]:
    config = get_strategy_config(conn, strategy_id)
    params = _normalize_params(config["params"], template_key=config["template_key"])
    params_hash = config["params_hash"]
    provider_key = provider.strip().lower() or "yahoo"
    canonical_symbol = symbol.strip().upper()
    window = _validated_window_trading_days(window_trading_days)
    indicator_engine_version = _engine_version_for_template(config["template_key"])
    archives = _recent_primary_archives(
        conn,
        provider=provider_key,
        symbol=canonical_symbol,
        end_date=end_date,
        limit=window,
    )
    archive_scope_hash = _archive_scope_hash(
        conn,
        template_key=config["template_key"],
        params=params,
        provider=provider_key,
        archives=archives,
    )
    idempotency_key = _strategy_test_idempotency_key(
        strategy_id=strategy_id,
        provider=provider_key,
        symbol=canonical_symbol,
        end_date=end_date,
        window_trading_days=window,
        archive_scope_hash=archive_scope_hash,
        params_hash=params_hash,
        template_version=config["template_version"],
        indicator_engine_version=indicator_engine_version,
    )
    existing = _find_strategy_test_batch_by_key(conn, idempotency_key)
    if existing and not force:
        return get_strategy_test_batch(conn, existing["id"])

    status = "completed"
    failure_reason: str | None = None
    day_results: list[dict[str, Any]] = []

    if not config["enabled"]:
        status = "strategy_disabled"
        failure_reason = "strategy_disabled"
    elif len(archives) < window:
        status = "insufficient_archive_coverage"
        failure_reason = f"required_{window}_archived_trading_days_found_{len(archives)}"

    if config["enabled"]:
        for archive in archives:
            run = _run_strategy_signal_replay_with_params(
                conn,
                strategy_id=strategy_id,
                trade_date=archive["trade_date"],
                symbol=canonical_symbol,
                provider=provider_key,
                params=params,
                params_hash=params_hash,
                template_key=config["template_key"],
                template_version=config["template_version"],
                enabled=config["enabled"],
                force=force,
            )
            day_results.append(_day_result_from_strategy_run(run))

    return _store_strategy_test_batch(
        conn,
        existing_batch_id=existing["id"] if existing else None,
        strategy_id=strategy_id,
        provider=provider_key,
        symbol=canonical_symbol,
        end_date=end_date,
        window_trading_days=window,
        archive_scope_hash=archive_scope_hash,
        params_json=_params_json(params),
        params_hash=params_hash,
        template_version=config["template_version"],
        indicator_engine_version=indicator_engine_version,
        status=status,
        failure_reason=failure_reason,
        day_results=day_results,
        idempotency_key=idempotency_key,
    )


def list_strategy_test_batches(
    conn: sqlite3.Connection,
    *,
    end_date: str | None = None,
    symbol: str | None = None,
    strategy_id: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if end_date:
        clauses.append("b.end_date = ?")
        params.append(end_date)
    if symbol:
        clauses.append("b.symbol = ?")
        params.append(symbol.strip().upper())
    if strategy_id:
        clauses.append("b.strategy_id = ?")
        params.append(strategy_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT b.*, c.name AS strategy_name, c.template_key
        FROM strategy_test_batches b
        JOIN strategy_configs c ON c.id = b.strategy_id
        {where}
        ORDER BY b.created_at DESC, b.id DESC
        """,
        params,
    ).fetchall()
    return [_public_strategy_test_batch(conn, row) for row in rows]


def get_strategy_test_batch(conn: sqlite3.Connection, batch_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT b.*, c.name AS strategy_name, c.template_key
        FROM strategy_test_batches b
        JOIN strategy_configs c ON c.id = b.strategy_id
        WHERE b.id = ?
        """,
        (batch_id,),
    ).fetchone()
    if not row:
        raise KeyError("strategy_test_batch_not_found")
    return _public_strategy_test_batch(conn, row)


def run_strategy_optimization(
    conn: sqlite3.Connection,
    *,
    strategy_id: str,
    end_date: str,
    symbol: str,
    provider: str = "yahoo",
    window_trading_days: int = DEFAULT_STRATEGY_TEST_WINDOW_DAYS,
    objective: str = DEFAULT_OPTIMIZATION_OBJECTIVE,
    search_space: dict[str, list[Any]] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if objective != DEFAULT_OPTIMIZATION_OBJECTIVE:
        raise ValueError("unsupported_strategy_optimization_objective")
    config = get_strategy_config(conn, strategy_id)
    base_params = _normalize_params(config["params"], template_key=config["template_key"])
    provider_key = provider.strip().lower() or "yahoo"
    canonical_symbol = symbol.strip().upper()
    window = _validated_window_trading_days(window_trading_days)
    indicator_engine_version = _engine_version_for_template(config["template_key"])
    archives = _recent_primary_archives(
        conn,
        provider=provider_key,
        symbol=canonical_symbol,
        end_date=end_date,
        limit=window,
    )
    archive_scope_hash = _archive_scope_hash(
        conn,
        template_key=config["template_key"],
        params=base_params,
        provider=provider_key,
        archives=archives,
    )
    normalized_search_space = _normalize_search_space(
        search_space,
        template_key=config["template_key"],
        enforce_candidate_cap=search_space is not None,
    )
    candidate_params = _candidate_params_from_search_space(
        base_params,
        normalized_search_space,
        template_key=config["template_key"],
        allow_sampling=search_space is None,
    )
    search_space_hash = _sha256_text(_json_payload(normalized_search_space))
    idempotency_key = _strategy_optimization_idempotency_key(
        strategy_id=strategy_id,
        provider=provider_key,
        symbol=canonical_symbol,
        end_date=end_date,
        window_trading_days=window,
        archive_scope_hash=archive_scope_hash,
        search_space_hash=search_space_hash,
        objective=objective,
        template_version=config["template_version"],
        indicator_engine_version=indicator_engine_version,
    )
    existing = _find_strategy_optimization_by_key(conn, idempotency_key)
    if existing and not force:
        return get_strategy_optimization_run(conn, existing["id"])

    status = "completed"
    failure_reason: str | None = None
    candidates: list[dict[str, Any]] = []

    if not config["enabled"]:
        status = "strategy_disabled"
        failure_reason = "strategy_disabled"
    elif len(archives) < window:
        status = "insufficient_archive_coverage"
        failure_reason = f"required_{window}_archived_trading_days_found_{len(archives)}"
    else:
        for params in candidate_params:
            candidates.append(
                _run_optimization_candidate(
                    conn,
                    strategy_id=strategy_id,
                    provider=provider_key,
                    symbol=canonical_symbol,
                    template_key=config["template_key"],
                    template_version=config["template_version"],
                    enabled=config["enabled"],
                    archives=archives,
                    params=params,
                    force=force,
                )
            )

    return _store_strategy_optimization_run(
        conn,
        existing_optimization_id=existing["id"] if existing else None,
        strategy_id=strategy_id,
        provider=provider_key,
        symbol=canonical_symbol,
        end_date=end_date,
        window_trading_days=window,
        archive_scope_hash=archive_scope_hash,
        search_space_json=_json_payload(normalized_search_space),
        search_space_hash=search_space_hash,
        objective=objective,
        template_version=config["template_version"],
        indicator_engine_version=indicator_engine_version,
        status=status,
        failure_reason=failure_reason,
        candidates=candidates,
        idempotency_key=idempotency_key,
    )


def list_strategy_optimization_runs(
    conn: sqlite3.Connection,
    *,
    end_date: str | None = None,
    symbol: str | None = None,
    strategy_id: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if end_date:
        clauses.append("o.end_date = ?")
        params.append(end_date)
    if symbol:
        clauses.append("o.symbol = ?")
        params.append(symbol.strip().upper())
    if strategy_id:
        clauses.append("o.strategy_id = ?")
        params.append(strategy_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT o.*, c.name AS strategy_name, c.template_key
        FROM strategy_optimization_runs o
        JOIN strategy_configs c ON c.id = o.strategy_id
        {where}
        ORDER BY o.created_at DESC, o.id DESC
        """,
        params,
    ).fetchall()
    return [_public_strategy_optimization_run(conn, row, include_candidates=False) for row in rows]


def get_strategy_optimization_run(conn: sqlite3.Connection, optimization_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT o.*, c.name AS strategy_name, c.template_key
        FROM strategy_optimization_runs o
        JOIN strategy_configs c ON c.id = o.strategy_id
        WHERE o.id = ?
        """,
        (optimization_id,),
    ).fetchone()
    if not row:
        raise KeyError("strategy_optimization_not_found")
    return _public_strategy_optimization_run(conn, row, include_candidates=True)


def evaluate_bb_squeeze_breakout(
    bars: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized = _normalize_params(params or DEFAULT_BB_SQUEEZE_PARAMS, template_key=BB_SQUEEZE_TEMPLATE_KEY)
    indicator_series = _indicator_series(bars, normalized)
    signals: list[dict[str, Any]] = []
    position: dict[str, Any] | None = None

    for index, bar in enumerate(bars):
        indicators = indicator_series[index]
        if position:
            exit_signal = _exit_signal(index, bar, indicators, position)
            if exit_signal:
                exit_signal["linked_entry_signal_index"] = position["entry_signal_index"]
                signals.append(exit_signal)
                position = None
            continue

        entry = _entry_signal(index, bar, indicator_series, normalized)
        if entry:
            entry["linked_entry_signal_index"] = None
            position = {
                "side": entry["side"],
                "entry_price": entry["price"],
                "stop_loss_price": entry["stop_loss_price"],
                "take_profit_price": entry["take_profit_price"],
                "entry_signal_index": len(signals),
            }
            signals.append(entry)

    return indicator_series, signals


def evaluate_institutional_liquidity_sweep(
    bars: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized = _normalize_params(params or DEFAULT_LIQUIDITY_SWEEP_PARAMS, template_key=LIQUIDITY_SWEEP_TEMPLATE_KEY)
    indicator_series = _liquidity_sweep_indicator_series(bars, normalized)
    signals: list[dict[str, Any]] = []
    position: dict[str, Any] | None = None

    for index, bar in enumerate(bars):
        indicators = indicator_series[index]
        if position:
            exit_signal = _liquidity_sweep_exit_signal(index, bar, indicators, position, normalized)
            if exit_signal:
                exit_signal["linked_entry_signal_index"] = position["entry_signal_index"]
                signals.append(exit_signal)
                position = None
            continue

        entry = _liquidity_sweep_entry_signal(index, bar, indicator_series, normalized)
        if entry:
            entry["linked_entry_signal_index"] = None
            position = {
                "side": entry["side"],
                "entry_price": entry["price"],
                "stop_loss_price": entry["stop_loss_price"],
                "take_profit_price": entry["take_profit_price"],
                "entry_signal_index": len(signals),
                "entry_bar_index": entry["bar_index"],
            }
            signals.append(entry)

    return indicator_series, signals


def evaluate_momentum_mean_reversion(
    bars: list[dict[str, Any]],
    context_bars: dict[str, list[dict[str, Any]]] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized = _normalize_params(
        params or DEFAULT_MOMENTUM_MEAN_REVERSION_PARAMS,
        template_key=MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY,
    )
    required_symbols = _momentum_context_symbols(normalized)
    supplied_context = context_bars or {}
    missing = [symbol for symbol in required_symbols if symbol not in supplied_context]
    if missing:
        raise ValueError("missing_momentum_context:" + ",".join(missing))

    indicator_series = _momentum_mean_reversion_indicator_series(bars, supplied_context, normalized)
    signals: list[dict[str, Any]] = []
    position: dict[str, Any] | None = None

    for index, bar in enumerate(bars):
        indicators = indicator_series[index]
        if position:
            exit_signal, close_position = _momentum_mean_reversion_exit_signal(index, bar, indicators, position, normalized)
            if exit_signal:
                exit_signal["linked_entry_signal_index"] = position["entry_signal_index"]
                signals.append(exit_signal)
                if close_position:
                    position = None
                else:
                    position["first_target_filled"] = True
                    position["stop_loss_price"] = position["entry_price"]
            continue

        entry = _momentum_mean_reversion_entry_signal(index, bar, bars, indicator_series, normalized)
        if entry:
            entry["linked_entry_signal_index"] = None
            position = {
                "side": entry["side"],
                "entry_price": entry["price"],
                "stop_loss_price": entry["stop_loss_price"],
                "take_profit_price": entry["take_profit_price"],
                "first_target_price": entry["metrics"]["first_target_price"],
                "first_target_filled": False,
                "entry_signal_index": len(signals),
            }
            signals.append(entry)

    return indicator_series, signals


def _evaluate_strategy(
    template_key: str,
    bars: list[dict[str, Any]],
    params: dict[str, Any],
    *,
    context_bars: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if template_key == BB_SQUEEZE_TEMPLATE_KEY:
        return evaluate_bb_squeeze_breakout(bars, params)
    if template_key == LIQUIDITY_SWEEP_TEMPLATE_KEY:
        return evaluate_institutional_liquidity_sweep(bars, params)
    if template_key == MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY:
        return evaluate_momentum_mean_reversion(bars, context_bars, params)
    raise ValueError("unsupported_strategy_template")


def _entry_signal(
    index: int,
    bar: dict[str, Any],
    indicator_series: list[dict[str, Any]],
    params: dict[str, Any],
) -> dict[str, Any] | None:
    indicators = indicator_series[index]
    required_keys = ("bb_upper", "bb_lower", "bb_middle", "rsi", "avg_volume", "relative_volume", "bandwidth")
    if any(indicators[key] is None for key in required_keys):
        return None
    if not _setup_ready(index, indicator_series, params):
        return None

    open_price = float(bar["open"])
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])
    volume = float(bar["volume"])
    body_ratio = _body_strength(open_price, high, low, close)
    absolute_bandwidth = float(indicators["bb_upper"]) - float(indicators["bb_lower"])
    if absolute_bandwidth <= float(params["min_absolute_bandwidth"]):
        return None
    volume_ok = volume >= float(indicators["avg_volume"]) * float(params["volume_multiplier"])
    strong_body = body_ratio >= float(params["body_strength_ratio"])

    if (
        close > open_price
        and close > float(indicators["bb_upper"])
        and volume_ok
        and strong_body
        and float(indicators["rsi"]) > 50
        and _setup_vwap_aligned(index, indicator_series, params, side="LONG")
    ):
        stop = round(max(float(indicators["bb_middle"]), low), 6)
        risk = close - stop
        if risk <= 0:
            return None
        take_profit = round(close + risk * float(params["risk_reward"]), 6)
        metrics = _entry_metrics(indicators, body_ratio, params, take_profit)
        return _signal(
            timestamp=str(bar["timestamp"]),
            bar_index=index,
            side="LONG",
            action="ENTRY_LONG",
            price=close,
            stop_loss_price=stop,
            take_profit_price=take_profit,
            reason_codes=[
                "squeeze_setup",
                "vwap_above",
                "absolute_bandwidth_filter",
                "upper_band_breakout",
                "volume_spike",
                "rsi_momentum",
                "passive_take_profit_order",
            ],
            metrics=metrics,
        )

    if (
        close < open_price
        and close < float(indicators["bb_lower"])
        and volume_ok
        and strong_body
        and float(indicators["rsi"]) < 50
        and _setup_vwap_aligned(index, indicator_series, params, side="SHORT")
    ):
        stop = round(min(float(indicators["bb_middle"]), high), 6)
        risk = stop - close
        if risk <= 0:
            return None
        take_profit = round(close - risk * float(params["risk_reward"]), 6)
        metrics = _entry_metrics(indicators, body_ratio, params, take_profit)
        return _signal(
            timestamp=str(bar["timestamp"]),
            bar_index=index,
            side="SHORT",
            action="ENTRY_SHORT",
            price=close,
            stop_loss_price=stop,
            take_profit_price=take_profit,
            reason_codes=[
                "squeeze_setup",
                "vwap_below",
                "absolute_bandwidth_filter",
                "lower_band_breakout",
                "volume_spike",
                "rsi_momentum",
                "passive_take_profit_order",
            ],
            metrics=metrics,
        )

    return None


def _exit_signal(
    index: int,
    bar: dict[str, Any],
    indicators: dict[str, Any],
    position: dict[str, Any],
) -> dict[str, Any] | None:
    close = float(bar["close"])
    high = float(bar["high"])
    low = float(bar["low"])
    side = position["side"]
    stop = float(position["stop_loss_price"])
    take_profit = float(position["take_profit_price"])
    middle = indicators.get("bb_middle")
    exit_ema = indicators.get("exit_ema")

    if side == "LONG":
        if low <= stop:
            reasons = ["stop_loss_hit"]
            price = stop
        elif high >= take_profit:
            reasons = ["risk_reward_target", "passive_take_profit_filled"]
            price = take_profit
        elif _long_exit_buffer_breached(close, middle, exit_ema):
            reasons = _exit_buffer_reasons(close, middle, exit_ema, side="LONG")
            price = close
        else:
            return None
        return _signal(
            timestamp=str(bar["timestamp"]),
            bar_index=index,
            side="LONG",
            action="EXIT_LONG",
            price=price,
            stop_loss_price=stop,
            take_profit_price=take_profit,
            reason_codes=reasons,
            metrics=_exit_metrics(position, price, indicators),
        )

    if high >= stop:
        reasons = ["stop_loss_hit"]
        price = stop
    elif low <= take_profit:
        reasons = ["risk_reward_target", "passive_take_profit_filled"]
        price = take_profit
    elif _short_exit_buffer_breached(close, middle, exit_ema):
        reasons = _exit_buffer_reasons(close, middle, exit_ema, side="SHORT")
        price = close
    else:
        return None
    return _signal(
        timestamp=str(bar["timestamp"]),
        bar_index=index,
        side="SHORT",
        action="EXIT_SHORT",
        price=price,
        stop_loss_price=stop,
        take_profit_price=take_profit,
        reason_codes=reasons,
        metrics=_exit_metrics(position, price, indicators),
    )


def _indicator_series(bars: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    bb_period = int(params["bb_period"])
    rsi_period = int(params["rsi_period"])
    volume_average_period = int(params["volume_average_period"])
    exit_ema_period = int(params["exit_ema_period"])
    closes: list[float] = []
    volumes: list[float] = []
    total_close_volume = 0.0
    total_volume = 0.0
    exit_ema_seed: float | None = None
    exit_ema_multiplier = 2.0 / (exit_ema_period + 1)
    series: list[dict[str, Any]] = []

    for index, bar in enumerate(bars):
        close = float(bar["close"])
        volume = float(bar["volume"])
        closes.append(close)
        volumes.append(volume)
        total_close_volume += close * volume
        total_volume += volume
        exit_ema_seed = close if exit_ema_seed is None else close * exit_ema_multiplier + exit_ema_seed * (1 - exit_ema_multiplier)

        middle = upper = lower = bandwidth = None
        if index + 1 >= bb_period:
            window = closes[index - bb_period + 1 : index + 1]
            middle = sum(window) / bb_period
            variance = sum((value - middle) ** 2 for value in window) / bb_period
            stddev = math.sqrt(variance)
            upper = middle + stddev * float(params["bb_stddev"])
            lower = middle - stddev * float(params["bb_stddev"])
            bandwidth = None if abs(middle) < 1e-12 else (upper - lower) / middle

        vwap = None if total_volume <= 0 else total_close_volume / total_volume
        rsi = _rsi(closes, rsi_period)
        avg_volume = None
        relative_volume = None
        if index >= volume_average_period:
            previous = volumes[index - volume_average_period : index]
            avg_volume = sum(previous) / len(previous)
            relative_volume = None if avg_volume <= 0 else volume / avg_volume

        series.append(
            {
                "timestamp": str(bar["timestamp"]),
                "bar_index": index,
                "close": round(close, 6),
                "bb_middle": _round_optional(middle),
                "bb_upper": _round_optional(upper),
                "bb_lower": _round_optional(lower),
                "bandwidth": _round_optional(bandwidth),
                "exit_ema": _round_optional(exit_ema_seed if index + 1 >= exit_ema_period else None),
                "vwap": _round_optional(vwap),
                "rsi": _round_optional(rsi),
                "avg_volume": _round_optional(avg_volume),
                "relative_volume": _round_optional(relative_volume),
            }
        )
    return series


def _liquidity_sweep_indicator_series(bars: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    bb_period = int(params["bb_period"])
    local_window = int(params["local_window"])
    volume_average_period = int(params["volume_average_period"])
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    volumes: list[float] = []
    total_close_volume = 0.0
    total_volume = 0.0
    series: list[dict[str, Any]] = []

    first_five_high: float | None = None
    first_five_low: float | None = None

    for index, bar in enumerate(bars):
        open_price = float(bar["open"])
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        volume = float(bar["volume"])
        closes.append(close)
        highs.append(high)
        lows.append(low)
        volumes.append(volume)
        total_close_volume += close * volume
        total_volume += volume

        if index < 5:
            first_five_high = high if first_five_high is None else max(first_five_high, high)
            first_five_low = low if first_five_low is None else min(first_five_low, low)

        middle = upper = lower = bandwidth = None
        if index + 1 >= bb_period:
            window = closes[index - bb_period + 1 : index + 1]
            middle = sum(window) / bb_period
            variance = sum((value - middle) ** 2 for value in window) / bb_period
            stddev = math.sqrt(variance)
            upper = middle + stddev * float(params["bb_stddev"])
            lower = middle - stddev * float(params["bb_stddev"])
            bandwidth = None if abs(middle) < 1e-12 else (upper - lower) / middle

        local_low = local_high = None
        if index >= local_window:
            local_lows = lows[index - local_window : index]
            local_highs = highs[index - local_window : index]
            local_low = min(local_lows)
            local_high = max(local_highs)

        avg_volume = None
        relative_volume = None
        if index >= volume_average_period:
            previous = volumes[index - volume_average_period : index]
            avg_volume = sum(previous) / len(previous)
            relative_volume = None if avg_volume <= 0 else volume / avg_volume

        candle_range = max(high - low, 1e-12)
        lower_shadow_ratio = (min(open_price, close) - low) / candle_range
        upper_shadow_ratio = (high - max(open_price, close)) / candle_range
        vwap = None if total_volume <= 0 else total_close_volume / total_volume

        series.append(
            {
                "timestamp": str(bar["timestamp"]),
                "bar_index": index,
                "close": round(close, 6),
                "bb_middle": _round_optional(middle),
                "bb_upper": _round_optional(upper),
                "bb_lower": _round_optional(lower),
                "bandwidth": _round_optional(bandwidth),
                "exit_ema": None,
                "vwap": _round_optional(vwap),
                "rsi": None,
                "avg_volume": _round_optional(avg_volume),
                "relative_volume": _round_optional(relative_volume),
                "local_low": _round_optional(local_low),
                "local_high": _round_optional(local_high),
                "first_five_high": _round_optional(first_five_high),
                "first_five_low": _round_optional(first_five_low),
                "lower_shadow_ratio": round(lower_shadow_ratio, 6),
                "upper_shadow_ratio": round(upper_shadow_ratio, 6),
            }
        )
    return series


def _liquidity_sweep_entry_signal(
    index: int,
    bar: dict[str, Any],
    indicator_series: list[dict[str, Any]],
    params: dict[str, Any],
) -> dict[str, Any] | None:
    indicators = indicator_series[index]
    required_keys = ("vwap", "avg_volume", "relative_volume", "bb_middle", "local_low", "local_high")
    if any(indicators[key] is None for key in required_keys):
        return None
    if index == 0 or indicator_series[index - 1]["vwap"] is None:
        return None

    open_price = float(bar["open"])
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])
    local_low = float(indicators["local_low"])
    local_high = float(indicators["local_high"])
    current_vwap = float(indicators["vwap"])
    previous = indicator_series[index - 1]
    previous_close = float(previous["close"])
    previous_vwap = float(previous["vwap"])
    relative_volume = float(indicators["relative_volume"])
    volume_ok = relative_volume >= float(params["volume_multiplier"])
    tick_offset = float(params["tick_size"]) * float(params["stop_tick_offset"])

    if (
        previous_close > previous_vwap
        and close > current_vwap
        and low < local_low
        and close > local_low
        and float(indicators["lower_shadow_ratio"]) >= float(params["shadow_ratio"])
        and volume_ok
    ):
        stop = round(low - tick_offset, 6)
        risk = close - stop
        if risk <= 0:
            return None
        take_profit = _liquidity_sweep_take_profit(
            entry_price=close,
            stop_loss_price=stop,
            bb_middle=float(indicators["bb_middle"]),
            params=params,
            side="LONG",
        )
        if take_profit <= close:
            return None
        return _signal(
            timestamp=str(bar["timestamp"]),
            bar_index=index,
            side="LONG",
            action="ENTRY_LONG",
            price=close,
            stop_loss_price=stop,
            take_profit_price=take_profit,
            reason_codes=[
                "liquidity_sweep_setup",
                "vwap_above",
                "local_low_swept",
                "pin_bar_reclaim",
                "volume_spike",
                "oco_immediate_mode",
                "passive_take_profit_order",
            ],
            metrics=_liquidity_sweep_entry_metrics(
                indicators,
                params,
                sweep_distance=local_low - low,
                take_profit_price=take_profit,
                stop_loss_price=stop,
                side="LONG",
            ),
        )

    if (
        previous_close < previous_vwap
        and close < current_vwap
        and high > local_high
        and close < local_high
        and float(indicators["upper_shadow_ratio"]) >= float(params["shadow_ratio"])
        and volume_ok
    ):
        stop = round(high + tick_offset, 6)
        risk = stop - close
        if risk <= 0:
            return None
        take_profit = _liquidity_sweep_take_profit(
            entry_price=close,
            stop_loss_price=stop,
            bb_middle=float(indicators["bb_middle"]),
            params=params,
            side="SHORT",
        )
        if take_profit >= close:
            return None
        return _signal(
            timestamp=str(bar["timestamp"]),
            bar_index=index,
            side="SHORT",
            action="ENTRY_SHORT",
            price=close,
            stop_loss_price=stop,
            take_profit_price=take_profit,
            reason_codes=[
                "liquidity_sweep_setup",
                "vwap_below",
                "local_high_swept",
                "pin_bar_reject",
                "volume_spike",
                "oco_immediate_mode",
                "passive_take_profit_order",
            ],
            metrics=_liquidity_sweep_entry_metrics(
                indicators,
                params,
                sweep_distance=high - local_high,
                take_profit_price=take_profit,
                stop_loss_price=stop,
                side="SHORT",
            ),
        )

    return None


def _liquidity_sweep_exit_signal(
    index: int,
    bar: dict[str, Any],
    indicators: dict[str, Any],
    position: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any] | None:
    close = float(bar["close"])
    high = float(bar["high"])
    low = float(bar["low"])
    side = position["side"]
    stop = float(position["stop_loss_price"])
    take_profit = float(position["take_profit_price"])
    holding_bars = index - int(position["entry_bar_index"])

    if side == "LONG":
        if low <= stop:
            reasons = ["stop_loss_hit"]
            price = stop
        elif high >= take_profit:
            reasons = _liquidity_take_profit_reasons(position, indicators)
            price = take_profit
        elif holding_bars >= int(params["max_holding_bars"]):
            reasons = ["max_holding_bars_elapsed"]
            price = close
        else:
            return None
        return _signal(
            timestamp=str(bar["timestamp"]),
            bar_index=index,
            side="LONG",
            action="EXIT_LONG",
            price=price,
            stop_loss_price=stop,
            take_profit_price=take_profit,
            reason_codes=reasons,
            metrics=_liquidity_sweep_exit_metrics(position, price, indicators, holding_bars),
        )

    if high >= stop:
        reasons = ["stop_loss_hit"]
        price = stop
    elif low <= take_profit:
        reasons = _liquidity_take_profit_reasons(position, indicators)
        price = take_profit
    elif holding_bars >= int(params["max_holding_bars"]):
        reasons = ["max_holding_bars_elapsed"]
        price = close
    else:
        return None
    return _signal(
        timestamp=str(bar["timestamp"]),
        bar_index=index,
        side="SHORT",
        action="EXIT_SHORT",
        price=price,
        stop_loss_price=stop,
        take_profit_price=take_profit,
        reason_codes=reasons,
        metrics=_liquidity_sweep_exit_metrics(position, price, indicators, holding_bars),
    )


def _liquidity_sweep_take_profit(
    *,
    entry_price: float,
    stop_loss_price: float,
    bb_middle: float,
    params: dict[str, Any],
    side: str,
) -> float:
    risk = abs(entry_price - stop_loss_price)
    if side == "LONG":
        risk_reward_target = entry_price + risk * float(params["risk_reward"])
        candidates = [risk_reward_target]
        if bb_middle > entry_price:
            candidates.append(bb_middle)
        return round(min(candidates), 6)
    risk_reward_target = entry_price - risk * float(params["risk_reward"])
    candidates = [risk_reward_target]
    if bb_middle < entry_price:
        candidates.append(bb_middle)
    return round(max(candidates), 6)


def _liquidity_sweep_entry_metrics(
    indicators: dict[str, Any],
    params: dict[str, Any],
    *,
    sweep_distance: float,
    take_profit_price: float,
    stop_loss_price: float,
    side: str,
) -> dict[str, float]:
    shadow_key = "lower_shadow_ratio" if side == "LONG" else "upper_shadow_ratio"
    return {
        "local_window": float(params["local_window"]),
        "local_low": float(indicators["local_low"]),
        "local_high": float(indicators["local_high"]),
        "vwap": float(indicators["vwap"]),
        "bb_middle": float(indicators["bb_middle"]),
        "avg_volume": float(indicators["avg_volume"]),
        "relative_volume": float(indicators["relative_volume"]),
        "shadow_ratio": float(indicators[shadow_key]),
        "required_shadow_ratio": float(params["shadow_ratio"]),
        "sweep_distance": round(float(sweep_distance), 6),
        "stop_loss_price": float(stop_loss_price),
        "passive_take_profit_price": float(take_profit_price),
        "risk_reward": float(params["risk_reward"]),
        "tick_size": float(params["tick_size"]),
        "stop_tick_offset": float(params["stop_tick_offset"]),
        "max_holding_bars": float(params["max_holding_bars"]),
    }


def _liquidity_sweep_exit_metrics(
    position: dict[str, Any],
    exit_price: float,
    indicators: dict[str, Any],
    holding_bars: int,
) -> dict[str, float]:
    metrics = _exit_metrics(position, exit_price, indicators)
    metrics["holding_bars"] = float(holding_bars)
    if indicators.get("vwap") is not None:
        metrics["vwap"] = float(indicators["vwap"])
    return metrics


def _liquidity_take_profit_reasons(position: dict[str, Any], indicators: dict[str, Any]) -> list[str]:
    reasons = ["passive_take_profit_filled"]
    middle = indicators.get("bb_middle")
    if middle is not None and abs(float(position["take_profit_price"]) - float(middle)) < 1e-6:
        reasons.insert(0, "middle_band_target")
    else:
        reasons.insert(0, "risk_reward_target")
    return reasons


def _momentum_mean_reversion_indicator_series(
    bars: list[dict[str, Any]],
    context_bars: dict[str, list[dict[str, Any]]],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    bb_period = int(params["bb_period"])
    atr_values = _average_true_range_series(bars, int(params["atr_period"]))
    adx_values = _adx_series(bars, int(params["adx_period"]))
    adx_trend_threshold = float(params["adx_trend_threshold"])
    adx_chop_threshold = float(params["adx_chop_threshold"])
    closes: list[float] = []
    total_close_volume = 0.0
    total_volume = 0.0
    context_maps = {
        symbol: _context_vwap_by_timestamp(context_bars[symbol]) for symbol in _momentum_context_symbols(params)
    }
    series: list[dict[str, Any]] = []
    trend_suppressed = False

    for index, bar in enumerate(bars):
        close = float(bar["close"])
        volume = float(bar["volume"])
        closes.append(close)
        total_close_volume += close * volume
        total_volume += volume

        middle = upper = lower = bandwidth = None
        if index + 1 >= bb_period:
            window = closes[index - bb_period + 1 : index + 1]
            middle = sum(window) / bb_period
            variance = sum((value - middle) ** 2 for value in window) / bb_period
            stddev = math.sqrt(variance)
            upper = middle + stddev * float(params["bb_stddev"])
            lower = middle - stddev * float(params["bb_stddev"])
            bandwidth = None if abs(middle) < 1e-12 else (upper - lower) / middle

        timestamp = str(bar["timestamp"])
        qqq_context = context_maps["QQQ"].get(timestamp)
        smh_context = context_maps["SMH"].get(timestamp)
        context_available = qqq_context is not None and smh_context is not None
        momentum_long = bool(
            context_available
            and float(qqq_context["close"]) > float(qqq_context["vwap"])
            and float(smh_context["close"]) > float(smh_context["vwap"])
        )
        momentum_short = bool(
            context_available
            and float(qqq_context["close"]) < float(qqq_context["vwap"])
            and float(smh_context["close"]) < float(smh_context["vwap"])
        )
        vwap = None if total_volume <= 0 else total_close_volume / total_volume
        atr = atr_values[index]
        adx = adx_values[index]
        market_regime = "unknown"
        mean_reversion_enabled = False
        if adx is not None:
            if adx > adx_trend_threshold:
                trend_suppressed = True
                market_regime = "trend"
            elif adx < adx_chop_threshold:
                trend_suppressed = False
                market_regime = "chop"
            else:
                market_regime = "neutral" if not trend_suppressed else "trend"
            mean_reversion_enabled = not trend_suppressed

        series.append(
            {
                "timestamp": timestamp,
                "bar_index": index,
                "close": round(close, 6),
                "bb_middle": _round_optional(middle),
                "bb_upper": _round_optional(upper),
                "bb_lower": _round_optional(lower),
                "bandwidth": _round_optional(bandwidth),
                "exit_ema": None,
                "vwap": _round_optional(vwap),
                "rsi": None,
                "avg_volume": None,
                "relative_volume": None,
                "time_window": 1 if _within_reversion_time_window(timestamp, params) else 0,
                "atr": _round_optional(atr),
                "adx": _round_optional(adx),
                "market_regime": market_regime,
                "mean_reversion_enabled": 1 if mean_reversion_enabled else 0,
                "momentum_long": 1 if momentum_long else 0,
                "momentum_short": 1 if momentum_short else 0,
                "qqq_close": _round_optional(None if qqq_context is None else float(qqq_context["close"])),
                "qqq_vwap": _round_optional(None if qqq_context is None else float(qqq_context["vwap"])),
                "smh_close": _round_optional(None if smh_context is None else float(smh_context["close"])),
                "smh_vwap": _round_optional(None if smh_context is None else float(smh_context["vwap"])),
            }
        )
    return series


def _momentum_mean_reversion_entry_signal(
    index: int,
    bar: dict[str, Any],
    bars: list[dict[str, Any]],
    indicator_series: list[dict[str, Any]],
    params: dict[str, Any],
) -> dict[str, Any] | None:
    indicators = indicator_series[index]
    if any(indicators[key] is None for key in ("bb_upper", "bb_lower", "bb_middle", "bandwidth", "vwap", "atr", "adx")):
        return None
    if not indicators["time_window"]:
        return None
    if not indicators.get("mean_reversion_enabled"):
        return None

    open_price = float(bar["open"])
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])
    upper = float(indicators["bb_upper"])
    middle = float(indicators["bb_middle"])
    lower = float(indicators["bb_lower"])
    atr_stop_distance = float(indicators["atr"]) * float(params["atr_stop_multiplier"])
    lookback_start = max(0, index - int(params["swing_lookback"]))
    recent_bars = bars[lookback_start : index + 1]
    previous_bar = bars[index - 1] if index > 0 else None
    long_pin = _long_reversal_pin_bar(open_price, high, low, close, float(params["pin_shadow_ratio"]))
    short_pin = _short_reversal_pin_bar(open_price, high, low, close, float(params["pin_shadow_ratio"]))
    bullish_engulfing = previous_bar is not None and _bullish_engulfing(previous_bar, bar)
    bearish_engulfing = previous_bar is not None and _bearish_engulfing(previous_bar, bar)

    if (
        indicators["momentum_long"]
        and low < lower
        and close > lower
        and (long_pin or bullish_engulfing)
        and middle > close
        and upper > close
    ):
        swing_low = min(float(item["low"]) for item in recent_bars)
        stop = round(close - atr_stop_distance, 6)
        if stop >= close:
            return None
        metrics = _momentum_mean_reversion_entry_metrics(
            indicators,
            params,
            first_target_price=middle,
            final_target_price=upper,
            stop_loss_price=stop,
            side="LONG",
            pin_bar=long_pin,
            engulfing=bullish_engulfing,
            swing_price=swing_low,
            atr_stop_distance=atr_stop_distance,
        )
        return _signal(
            timestamp=str(bar["timestamp"]),
            bar_index=index,
            side="LONG",
            action="ENTRY_LONG",
            price=close,
            stop_loss_price=stop,
            take_profit_price=upper,
            reason_codes=[
                _reversion_time_window_reason(params),
                "regime_chop_adx",
                "momentum_filter_long",
                "lower_band_observation",
                "reversal_reclaim_lower_band",
                "pin_bar_reclaim" if long_pin else "bullish_engulfing",
                "atr_dynamic_stop",
                "partial_take_profit_plan",
                "break_even_after_middle_target",
            ],
            metrics=metrics,
        )

    if (
        indicators["momentum_short"]
        and high > upper
        and close < upper
        and (short_pin or bearish_engulfing)
        and middle < close
        and lower < close
    ):
        swing_high = max(float(item["high"]) for item in recent_bars)
        stop = round(close + atr_stop_distance, 6)
        if stop <= close:
            return None
        metrics = _momentum_mean_reversion_entry_metrics(
            indicators,
            params,
            first_target_price=middle,
            final_target_price=lower,
            stop_loss_price=stop,
            side="SHORT",
            pin_bar=short_pin,
            engulfing=bearish_engulfing,
            swing_price=swing_high,
            atr_stop_distance=atr_stop_distance,
        )
        return _signal(
            timestamp=str(bar["timestamp"]),
            bar_index=index,
            side="SHORT",
            action="ENTRY_SHORT",
            price=close,
            stop_loss_price=stop,
            take_profit_price=lower,
            reason_codes=[
                _reversion_time_window_reason(params),
                "regime_chop_adx",
                "momentum_filter_short",
                "upper_band_observation",
                "reversal_reject_upper_band",
                "pin_bar_reject" if short_pin else "bearish_engulfing",
                "atr_dynamic_stop",
                "partial_take_profit_plan",
                "break_even_after_middle_target",
            ],
            metrics=metrics,
        )

    return None


def _momentum_mean_reversion_exit_signal(
    index: int,
    bar: dict[str, Any],
    indicators: dict[str, Any],
    position: dict[str, Any],
    params: dict[str, Any],
) -> tuple[dict[str, Any] | None, bool]:
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])
    side = position["side"]
    stop = float(position["stop_loss_price"])
    first_target = float(position["first_target_price"])
    final_target = float(position["take_profit_price"])
    first_target_filled = bool(position.get("first_target_filled"))

    if side == "LONG":
        if low <= stop:
            reasons = ["break_even_stop_hit"] if first_target_filled else ["stop_loss_hit", "mean_reversion_failed"]
            price = stop
            return (
                _signal(
                    timestamp=str(bar["timestamp"]),
                    bar_index=index,
                    side="LONG",
                    action="EXIT_LONG",
                    price=price,
                    stop_loss_price=stop,
                    take_profit_price=final_target,
                    reason_codes=reasons,
                    metrics=_momentum_mean_reversion_exit_metrics(position, price, indicators, 1.0 if not first_target_filled else _remaining_exit_fraction(params)),
                ),
                True,
            )
        if not first_target_filled and high >= first_target:
            return (
                _signal(
                    timestamp=str(bar["timestamp"]),
                    bar_index=index,
                    side="LONG",
                    action="EXIT_LONG",
                    price=first_target,
                    stop_loss_price=float(position["entry_price"]),
                    take_profit_price=final_target,
                    reason_codes=["middle_band_first_target", "partial_take_profit_filled", "break_even_stop_armed"],
                    metrics=_momentum_mean_reversion_exit_metrics(
                        position,
                        first_target,
                        indicators,
                        float(params["first_target_exit_fraction"]),
                        break_even_stop_activated=True,
                    ),
                ),
                False,
            )
        if first_target_filled and high >= final_target:
            return (
                _signal(
                    timestamp=str(bar["timestamp"]),
                    bar_index=index,
                    side="LONG",
                    action="EXIT_LONG",
                    price=final_target,
                    stop_loss_price=stop,
                    take_profit_price=final_target,
                    reason_codes=["upper_band_final_target", "remaining_take_profit_filled"],
                    metrics=_momentum_mean_reversion_exit_metrics(position, final_target, indicators, _remaining_exit_fraction(params)),
                ),
                True,
            )
        return None, False

    if high >= stop:
        reasons = ["break_even_stop_hit"] if first_target_filled else ["stop_loss_hit", "mean_reversion_failed"]
        price = stop
        return (
            _signal(
                timestamp=str(bar["timestamp"]),
                bar_index=index,
                side="SHORT",
                action="EXIT_SHORT",
                price=price,
                stop_loss_price=stop,
                take_profit_price=final_target,
                reason_codes=reasons,
                metrics=_momentum_mean_reversion_exit_metrics(position, price, indicators, 1.0 if not first_target_filled else _remaining_exit_fraction(params)),
            ),
            True,
        )
    if not first_target_filled and low <= first_target:
        return (
            _signal(
                timestamp=str(bar["timestamp"]),
                bar_index=index,
                side="SHORT",
                action="EXIT_SHORT",
                price=first_target,
                stop_loss_price=float(position["entry_price"]),
                take_profit_price=final_target,
                reason_codes=["middle_band_first_target", "partial_take_profit_filled", "break_even_stop_armed"],
                metrics=_momentum_mean_reversion_exit_metrics(
                    position,
                    first_target,
                    indicators,
                    float(params["first_target_exit_fraction"]),
                    break_even_stop_activated=True,
                ),
            ),
            False,
        )
    if first_target_filled and low <= final_target:
        return (
            _signal(
                timestamp=str(bar["timestamp"]),
                bar_index=index,
                side="SHORT",
                action="EXIT_SHORT",
                price=final_target,
                stop_loss_price=stop,
                take_profit_price=final_target,
                reason_codes=["lower_band_final_target", "remaining_take_profit_filled"],
                metrics=_momentum_mean_reversion_exit_metrics(position, final_target, indicators, _remaining_exit_fraction(params)),
            ),
            True,
        )
    return None, False


def _momentum_mean_reversion_entry_metrics(
    indicators: dict[str, Any],
    params: dict[str, Any],
    *,
    first_target_price: float,
    final_target_price: float,
    stop_loss_price: float,
    side: str,
    pin_bar: bool,
    engulfing: bool,
    swing_price: float,
    atr_stop_distance: float,
) -> dict[str, float]:
    return {
        "bb_middle": float(indicators["bb_middle"]),
        "bb_upper": float(indicators["bb_upper"]),
        "bb_lower": float(indicators["bb_lower"]),
        "bandwidth": float(indicators["bandwidth"]),
        "vwap": float(indicators["vwap"]),
        "atr": float(indicators["atr"]),
        "adx": float(indicators["adx"]),
        "adx_trend_threshold": float(params["adx_trend_threshold"]),
        "adx_chop_threshold": float(params["adx_chop_threshold"]),
        "market_regime_code": float(_market_regime_code(indicators.get("market_regime"))),
        "mean_reversion_enabled": float(indicators["mean_reversion_enabled"]),
        "qqq_close": float(indicators["qqq_close"]),
        "qqq_vwap": float(indicators["qqq_vwap"]),
        "smh_close": float(indicators["smh_close"]),
        "smh_vwap": float(indicators["smh_vwap"]),
        "stop_loss_price": float(stop_loss_price),
        "first_target_price": float(first_target_price),
        "final_target_price": float(final_target_price),
        "first_target_exit_fraction": float(params["first_target_exit_fraction"]),
        "tick_size": float(params["tick_size"]),
        "atr_stop_multiplier": float(params["atr_stop_multiplier"]),
        "atr_stop_distance": float(atr_stop_distance),
        "pin_bar": 1.0 if pin_bar else 0.0,
        "engulfing": 1.0 if engulfing else 0.0,
        "swing_low" if side == "LONG" else "swing_high": float(swing_price),
    }


def _momentum_mean_reversion_exit_metrics(
    position: dict[str, Any],
    exit_price: float,
    indicators: dict[str, Any],
    exit_fraction: float,
    *,
    break_even_stop_activated: bool = False,
) -> dict[str, float]:
    metrics = _exit_metrics(position, exit_price, indicators)
    metrics["exit_fraction"] = float(exit_fraction)
    metrics["first_target_price"] = float(position["first_target_price"])
    metrics["final_target_price"] = float(position["take_profit_price"])
    metrics["break_even_stop_activated"] = 1.0 if break_even_stop_activated else 0.0
    if indicators.get("atr") is not None:
        metrics["atr"] = float(indicators["atr"])
    if indicators.get("adx") is not None:
        metrics["adx"] = float(indicators["adx"])
    if indicators.get("mean_reversion_enabled") is not None:
        metrics["mean_reversion_enabled"] = float(indicators["mean_reversion_enabled"])
    return metrics


def _remaining_exit_fraction(params: dict[str, Any]) -> float:
    return round(1.0 - float(params["first_target_exit_fraction"]), 6)


def _context_vwap_by_timestamp(bars: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    total_close_volume = 0.0
    total_volume = 0.0
    payload: dict[str, dict[str, float]] = {}
    for bar in bars:
        close = float(bar["close"])
        volume = float(bar["volume"])
        total_close_volume += close * volume
        total_volume += volume
        if total_volume > 0:
            payload[str(bar["timestamp"])] = {"close": close, "vwap": total_close_volume / total_volume}
    return payload


def _average_true_range_series(bars: list[dict[str, Any]], period: int) -> list[float | None]:
    true_ranges: list[float] = []
    atr_values: list[float | None] = []
    previous_close: float | None = None

    for index, bar in enumerate(bars):
        high = float(bar["high"])
        low = float(bar["low"])
        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(true_range)
        previous_close = float(bar["close"])

        if index + 1 < period:
            atr_values.append(None)
        else:
            window = true_ranges[index - period + 1 : index + 1]
            atr_values.append(sum(window) / period)

    return atr_values


def _adx_series(bars: list[dict[str, Any]], period: int) -> list[float | None]:
    true_ranges: list[float] = []
    plus_dm_values: list[float] = []
    minus_dm_values: list[float] = []
    dx_values: list[float | None] = []
    adx_values: list[float | None] = []
    previous_high: float | None = None
    previous_low: float | None = None
    previous_close: float | None = None

    for index, bar in enumerate(bars):
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        if previous_high is None or previous_low is None or previous_close is None:
            true_range = high - low
            plus_dm = 0.0
            minus_dm = 0.0
        else:
            true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
            up_move = high - previous_high
            down_move = previous_low - low
            plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
            minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0

        true_ranges.append(true_range)
        plus_dm_values.append(plus_dm)
        minus_dm_values.append(minus_dm)
        previous_high = high
        previous_low = low
        previous_close = close

        if index + 1 < period:
            dx_values.append(None)
            adx_values.append(None)
            continue

        tr_sum = sum(true_ranges[index - period + 1 : index + 1])
        if tr_sum <= 1e-12:
            dx = 0.0
        else:
            plus_di = 100.0 * sum(plus_dm_values[index - period + 1 : index + 1]) / tr_sum
            minus_di = 100.0 * sum(minus_dm_values[index - period + 1 : index + 1]) / tr_sum
            denominator = plus_di + minus_di
            dx = 0.0 if denominator <= 1e-12 else 100.0 * abs(plus_di - minus_di) / denominator

        dx_values.append(dx)
        dx_window = [value for value in dx_values[max(0, index - period + 1) : index + 1] if value is not None]
        adx_values.append(None if not dx_window else sum(dx_window) / len(dx_window))

    return adx_values


def _within_reversion_time_window(timestamp: str, params: dict[str, Any]) -> bool:
    minute = _clock_minute(timestamp)
    if minute is None:
        return False
    start = int(params["start_hour"]) * 60 + int(params["start_minute"])
    end = int(params["end_hour"]) * 60 + int(params["end_minute"])
    return start <= minute <= end


def _reversion_time_window_reason(params: dict[str, Any]) -> str:
    start = int(params["start_hour"]) * 60 + int(params["start_minute"])
    end = int(params["end_hour"]) * 60 + int(params["end_minute"])
    return f"time_window_{start // 60:02d}{start % 60:02d}_{end // 60:02d}{end % 60:02d}"


def _market_regime_code(regime: Any) -> int:
    return {"unknown": 0, "chop": 1, "neutral": 2, "trend": 3}.get(str(regime), 0)


def _long_reversal_pin_bar(open_price: float, high: float, low: float, close: float, required_ratio: float) -> bool:
    candle_range = max(high - low, 1e-12)
    lower_shadow_ratio = (min(open_price, close) - low) / candle_range
    return lower_shadow_ratio >= required_ratio and close >= low + candle_range * 0.5


def _short_reversal_pin_bar(open_price: float, high: float, low: float, close: float, required_ratio: float) -> bool:
    candle_range = max(high - low, 1e-12)
    upper_shadow_ratio = (high - max(open_price, close)) / candle_range
    return upper_shadow_ratio >= required_ratio and close <= high - candle_range * 0.5


def _bullish_engulfing(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    previous_open = float(previous["open"])
    previous_close = float(previous["close"])
    current_open = float(current["open"])
    current_close = float(current["close"])
    return previous_close < previous_open and current_close > current_open and current_open <= previous_close and current_close >= previous_open


def _bearish_engulfing(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    previous_open = float(previous["open"])
    previous_close = float(previous["close"])
    current_open = float(current["open"])
    current_close = float(current["close"])
    return previous_close > previous_open and current_close < current_open and current_open >= previous_close and current_close <= previous_open


def _clock_minute(timestamp: str) -> int | None:
    value = str(timestamp)
    if "T" in value:
        clock = value.split("T", 1)[1]
    else:
        clock = value
    parts = clock.split(":", 2)
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return None


def _rsi(closes: list[float], period: int) -> float | None:
    if len(closes) <= period:
        return None
    changes = [closes[index] - closes[index - 1] for index in range(len(closes) - period, len(closes))]
    gains = [max(change, 0.0) for change in changes]
    losses = [abs(min(change, 0.0)) for change in changes]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _setup_ready(index: int, series: list[dict[str, Any]], params: dict[str, Any]) -> bool:
    setup_minutes = int(params["setup_minutes"])
    if index < setup_minutes:
        return False
    setup = series[index - setup_minutes : index]
    if any(item["bb_upper"] is None or item["bb_lower"] is None or item["bandwidth"] is None for item in setup):
        return False
    prior_bandwidths = [float(item["bandwidth"]) for item in series[:index] if item["bandwidth"] is not None]
    if len(prior_bandwidths) < setup_minutes:
        return False
    threshold = _percentile(prior_bandwidths, float(params["squeeze_percentile"]))
    if max(float(item["bandwidth"]) for item in setup) > threshold:
        return False
    return all(float(item["bb_lower"]) <= float(item["close"]) <= float(item["bb_upper"]) for item in setup)


def _setup_vwap_aligned(index: int, series: list[dict[str, Any]], params: dict[str, Any], *, side: str) -> bool:
    setup = series[index - int(params["setup_minutes"]) : index]
    if any(item["vwap"] is None for item in setup):
        return False
    if side == "LONG":
        return all(float(item["close"]) > float(item["vwap"]) for item in setup)
    return all(float(item["close"]) < float(item["vwap"]) for item in setup)


def _body_strength(open_price: float, high: float, low: float, close: float) -> float:
    candle_range = max(high - low, 1e-12)
    return abs(close - open_price) / candle_range


def _entry_metrics(
    indicators: dict[str, Any],
    body_ratio: float,
    params: dict[str, Any],
    take_profit_price: float,
) -> dict[str, float]:
    absolute_bandwidth = float(indicators["bb_upper"]) - float(indicators["bb_lower"])
    return {
        "bb_middle": float(indicators["bb_middle"]),
        "bb_upper": float(indicators["bb_upper"]),
        "bb_lower": float(indicators["bb_lower"]),
        "bandwidth": float(indicators["bandwidth"]),
        "absolute_bandwidth": absolute_bandwidth,
        "min_absolute_bandwidth": float(params["min_absolute_bandwidth"]),
        "vwap": float(indicators["vwap"]),
        "rsi": float(indicators["rsi"]),
        "relative_volume": float(indicators["relative_volume"]),
        "body_strength": round(body_ratio, 6),
        "passive_take_profit_price": float(take_profit_price),
    }


def _exit_metrics(position: dict[str, Any], exit_price: float, indicators: dict[str, Any]) -> dict[str, float]:
    entry_price = float(position["entry_price"])
    direction = 1.0 if position["side"] == "LONG" else -1.0
    metrics = {
        "entry_price": entry_price,
        "exit_price": round(float(exit_price), 6),
        "pnl_per_share": round((float(exit_price) - entry_price) * direction, 6),
    }
    if indicators.get("bb_middle") is not None:
        metrics["bb_middle"] = float(indicators["bb_middle"])
    if indicators.get("exit_ema") is not None:
        metrics["exit_ema"] = float(indicators["exit_ema"])
    return metrics


def _long_exit_buffer_breached(close: float, middle: Any, exit_ema: Any) -> bool:
    return (exit_ema is not None and close < float(exit_ema)) or (middle is not None and close < float(middle))


def _short_exit_buffer_breached(close: float, middle: Any, exit_ema: Any) -> bool:
    return (exit_ema is not None and close > float(exit_ema)) or (middle is not None and close > float(middle))


def _exit_buffer_reasons(close: float, middle: Any, exit_ema: Any, *, side: str) -> list[str]:
    reasons: list[str] = []
    if exit_ema is not None:
        if (side == "LONG" and close < float(exit_ema)) or (side == "SHORT" and close > float(exit_ema)):
            reasons.append("exit_ema_breached")
    if middle is not None:
        if (side == "LONG" and close < float(middle)) or (side == "SHORT" and close > float(middle)):
            reasons.append("middle_band_breached")
    return reasons or ["exit_buffer_breached"]


def _signal(
    *,
    timestamp: str,
    bar_index: int,
    side: str,
    action: str,
    price: float,
    stop_loss_price: float,
    take_profit_price: float,
    reason_codes: list[str],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "bar_index": int(bar_index),
        "side": side,
        "action": action,
        "price": round(float(price), 6),
        "stop_loss_price": round(float(stop_loss_price), 6),
        "take_profit_price": round(float(take_profit_price), 6),
        "reason_codes": reason_codes,
        "metrics": {key: _round_value(value) for key, value in metrics.items()},
    }


def _store_strategy_run(
    conn: sqlite3.Connection,
    *,
    existing_run_id: str | None,
    strategy_id: str,
    provider: str,
    symbol: str,
    trade_date: str,
    source_archive_id: str | None,
    bars_hash: str,
    params_hash: str,
    params_json: str,
    status: str,
    failure_reason: str | None,
    indicator_series: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    idempotency_key: str,
    indicator_engine_version: str,
) -> dict[str, Any]:
    if status not in RUN_STATUSES:
        raise ValueError(f"unsupported_strategy_run_status:{status}")

    indicator_json = _json_payload(indicator_series)
    indicator_hash = _sha256_text(indicator_json)
    created_at = _now()
    run_id = existing_run_id or new_id("stratrun")
    with conn:
        if existing_run_id:
            conn.execute("DELETE FROM strategy_signals WHERE run_id = ?", (run_id,))
            conn.execute(
                """
                UPDATE strategy_signal_runs
                SET source_archive_id = ?, bars_hash = ?, params_hash = ?, params_json = ?,
                    indicator_engine_version = ?, status = ?, failure_reason = ?,
                    indicator_series_json = ?, indicator_hash = ?, signal_count = ?,
                    created_at = ?
                WHERE id = ?
                """,
                (
                    source_archive_id,
                    bars_hash,
                    params_hash,
                    params_json,
                    indicator_engine_version,
                    status,
                    failure_reason,
                    indicator_json,
                    indicator_hash,
                    len(signals),
                    created_at,
                    run_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO strategy_signal_runs (
                    id, strategy_id, provider, symbol, trade_date, source_archive_id,
                    bars_hash, params_hash, params_json, indicator_engine_version, status,
                    failure_reason, indicator_series_json, indicator_hash, signal_count,
                    idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    strategy_id,
                    provider,
                    symbol,
                    trade_date,
                    source_archive_id,
                    bars_hash,
                    params_hash,
                    params_json,
                    indicator_engine_version,
                    status,
                    failure_reason,
                    indicator_json,
                    indicator_hash,
                    len(signals),
                    idempotency_key,
                    created_at,
                ),
            )
        _insert_signals(conn, run_id, signals)
    return get_strategy_signal_run(conn, run_id)


def _store_strategy_test_batch(
    conn: sqlite3.Connection,
    *,
    existing_batch_id: str | None,
    strategy_id: str,
    provider: str,
    symbol: str,
    end_date: str,
    window_trading_days: int,
    archive_scope_hash: str,
    params_json: str,
    params_hash: str,
    template_version: str,
    indicator_engine_version: str,
    status: str,
    failure_reason: str | None,
    day_results: list[dict[str, Any]],
    idempotency_key: str,
) -> dict[str, Any]:
    if status not in STRATEGY_TEST_BATCH_STATUSES:
        raise ValueError(f"unsupported_strategy_test_batch_status:{status}")
    metrics = _aggregate_day_results(day_results, window_trading_days=window_trading_days)
    created_at = _now()
    batch_id = existing_batch_id or new_id("strattest")
    with conn:
        if existing_batch_id:
            conn.execute("DELETE FROM strategy_test_day_results WHERE batch_id = ?", (batch_id,))
            conn.execute(
                """
                UPDATE strategy_test_batches
                SET archive_scope_hash = ?, params_json = ?, params_hash = ?, template_version = ?,
                    indicator_engine_version = ?, status = ?, failure_reason = ?, day_count = ?,
                    available_day_count = ?, completed_day_count = ?, signal_count = ?, total_pnl = ?,
                    win_rate = ?, profit_factor = ?, max_drawdown = ?, coverage_ratio = ?, created_at = ?
                WHERE id = ?
                """,
                (
                    archive_scope_hash,
                    params_json,
                    params_hash,
                    template_version,
                    indicator_engine_version,
                    status,
                    failure_reason,
                    len(day_results),
                    metrics["available_day_count"],
                    metrics["completed_day_count"],
                    metrics["signal_count"],
                    metrics["total_pnl"],
                    metrics["win_rate"],
                    metrics["profit_factor"],
                    metrics["max_drawdown"],
                    metrics["coverage_ratio"],
                    created_at,
                    batch_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO strategy_test_batches (
                    id, strategy_id, provider, symbol, end_date, window_trading_days,
                    archive_scope_hash, params_json, params_hash, template_version,
                    indicator_engine_version, status, failure_reason, day_count,
                    available_day_count, completed_day_count, signal_count, total_pnl,
                    win_rate, profit_factor, max_drawdown, coverage_ratio, idempotency_key,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    strategy_id,
                    provider,
                    symbol,
                    end_date,
                    window_trading_days,
                    archive_scope_hash,
                    params_json,
                    params_hash,
                    template_version,
                    indicator_engine_version,
                    status,
                    failure_reason,
                    len(day_results),
                    metrics["available_day_count"],
                    metrics["completed_day_count"],
                    metrics["signal_count"],
                    metrics["total_pnl"],
                    metrics["win_rate"],
                    metrics["profit_factor"],
                    metrics["max_drawdown"],
                    metrics["coverage_ratio"],
                    idempotency_key,
                    created_at,
                ),
            )
        _insert_strategy_test_day_results(conn, batch_id, day_results, created_at)
    return get_strategy_test_batch(conn, batch_id)


def _insert_strategy_test_day_results(
    conn: sqlite3.Connection,
    batch_id: str,
    day_results: list[dict[str, Any]],
    created_at: str,
) -> None:
    for day in day_results:
        conn.execute(
            """
            INSERT INTO strategy_test_day_results (
                id, batch_id, trade_date, source_archive_id, bars_hash, strategy_run_id,
                status, failure_reason, signal_count, total_pnl, win_rate, profit_factor,
                closed_group_count, indicator_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("strattestday"),
                batch_id,
                day["trade_date"],
                day["source_archive_id"],
                day["bars_hash"],
                day["strategy_run_id"],
                day["status"],
                day["failure_reason"],
                day["signal_count"],
                day["total_pnl"],
                day["win_rate"],
                day["profit_factor"],
                day["closed_group_count"],
                day["indicator_hash"],
                created_at,
            ),
        )


def _store_strategy_optimization_run(
    conn: sqlite3.Connection,
    *,
    existing_optimization_id: str | None,
    strategy_id: str,
    provider: str,
    symbol: str,
    end_date: str,
    window_trading_days: int,
    archive_scope_hash: str,
    search_space_json: str,
    search_space_hash: str,
    objective: str,
    template_version: str,
    indicator_engine_version: str,
    status: str,
    failure_reason: str | None,
    candidates: list[dict[str, Any]],
    idempotency_key: str,
) -> dict[str, Any]:
    if status not in STRATEGY_OPTIMIZATION_STATUSES:
        raise ValueError(f"unsupported_strategy_optimization_status:{status}")
    ranked_candidates = _rank_optimization_candidates(candidates)
    best_candidate = next((candidate for candidate in ranked_candidates if candidate["status"] == "eligible"), None)
    created_at = _now()
    optimization_id = existing_optimization_id or new_id("stratopt")
    with conn:
        if existing_optimization_id:
            conn.execute("DELETE FROM strategy_optimization_candidates WHERE optimization_run_id = ?", (optimization_id,))
            conn.execute(
                """
                UPDATE strategy_optimization_runs
                SET archive_scope_hash = ?, search_space_json = ?, search_space_hash = ?, objective = ?,
                    template_version = ?, indicator_engine_version = ?, status = ?, failure_reason = ?,
                    candidate_count = ?, eligible_candidate_count = ?, best_candidate_id = ?,
                    best_params_hash = ?, best_stability_score = ?, created_at = ?
                WHERE id = ?
                """,
                (
                    archive_scope_hash,
                    search_space_json,
                    search_space_hash,
                    objective,
                    template_version,
                    indicator_engine_version,
                    status,
                    failure_reason,
                    len(ranked_candidates),
                    sum(1 for candidate in ranked_candidates if candidate["status"] == "eligible"),
                    best_candidate["candidate_id"] if best_candidate else None,
                    best_candidate["params_hash"] if best_candidate else None,
                    best_candidate["stability_score"] if best_candidate else None,
                    created_at,
                    optimization_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO strategy_optimization_runs (
                    id, strategy_id, provider, symbol, end_date, window_trading_days,
                    archive_scope_hash, search_space_json, search_space_hash, objective,
                    template_version, indicator_engine_version, status, failure_reason,
                    candidate_count, eligible_candidate_count, best_candidate_id,
                    best_params_hash, best_stability_score, idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    optimization_id,
                    strategy_id,
                    provider,
                    symbol,
                    end_date,
                    window_trading_days,
                    archive_scope_hash,
                    search_space_json,
                    search_space_hash,
                    objective,
                    template_version,
                    indicator_engine_version,
                    status,
                    failure_reason,
                    len(ranked_candidates),
                    sum(1 for candidate in ranked_candidates if candidate["status"] == "eligible"),
                    best_candidate["candidate_id"] if best_candidate else None,
                    best_candidate["params_hash"] if best_candidate else None,
                    best_candidate["stability_score"] if best_candidate else None,
                    idempotency_key,
                    created_at,
                ),
            )
        _insert_strategy_optimization_candidates(conn, optimization_id, ranked_candidates, created_at)
    return get_strategy_optimization_run(conn, optimization_id)


def _insert_strategy_optimization_candidates(
    conn: sqlite3.Connection,
    optimization_id: str,
    candidates: list[dict[str, Any]],
    created_at: str,
) -> None:
    for candidate in candidates:
        if candidate["status"] not in STRATEGY_OPTIMIZATION_CANDIDATE_STATUSES:
            raise ValueError(f"unsupported_strategy_optimization_candidate_status:{candidate['status']}")
        conn.execute(
            """
            INSERT INTO strategy_optimization_candidates (
                id, optimization_run_id, rank, params_json, params_hash, day_results_json,
                status, failure_reason, total_pnl, win_rate, profit_factor, max_drawdown,
                closed_group_count, coverage_ratio, stability_score, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate["candidate_id"],
                optimization_id,
                candidate["rank"],
                candidate["params_json"],
                candidate["params_hash"],
                candidate["day_results_json"],
                candidate["status"],
                candidate["failure_reason"],
                candidate["total_pnl"],
                candidate["win_rate"],
                candidate["profit_factor"],
                candidate["max_drawdown"],
                candidate["closed_group_count"],
                candidate["coverage_ratio"],
                candidate["stability_score"],
                created_at,
            ),
        )


def _insert_signals(conn: sqlite3.Connection, run_id: str, signals: list[dict[str, Any]]) -> None:
    signal_ids: dict[int, str] = {}
    for index, signal in enumerate(signals):
        signal_id = new_id("signal")
        signal_ids[index] = signal_id
        linked_index = signal.get("linked_entry_signal_index")
        linked_id = signal_ids.get(linked_index) if linked_index is not None else None
        conn.execute(
            """
            INSERT INTO strategy_signals (
                id, run_id, timestamp, bar_index, side, action, price,
                stop_loss_price, take_profit_price, linked_entry_signal_id,
                reason_codes_json, metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                run_id,
                signal["timestamp"],
                int(signal["bar_index"]),
                signal["side"],
                signal["action"],
                float(signal["price"]),
                signal.get("stop_loss_price"),
                signal.get("take_profit_price"),
                linked_id,
                _json_payload(signal["reason_codes"]),
                _json_payload(signal["metrics"]),
            ),
        )


def _public_strategy_config(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["strategy_id"] = payload["id"]
    payload["enabled"] = bool(payload["enabled"])
    payload["params"] = json.loads(payload["params_json"])
    return payload


def _public_strategy_run(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["run_id"] = payload["id"]
    payload["signal_count"] = int(payload["signal_count"])
    payload["indicator_series"] = json.loads(payload["indicator_series_json"])
    payload["signals"] = _public_signals(conn, payload["id"])
    payload["signal_performance"] = _strategy_signal_performance(payload["signals"])
    run_params = _run_params_from_payload(payload)
    payload["strategy"] = {
        "strategy_id": payload["strategy_id"],
        "name": payload["strategy_name"],
        "template_key": payload["template_key"],
        "template_version": payload["template_version"],
        "params": run_params,
    }
    payload["params"] = run_params
    return payload


def _run_params_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    config_params = json.loads(payload.get("strategy_config_params_json") or "{}")
    run_params = json.loads(payload.get("params_json") or "{}")
    return run_params or config_params


def _public_strategy_test_batch(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["batch_id"] = payload["id"]
    payload["window_trading_days"] = int(payload["window_trading_days"])
    payload["day_count"] = int(payload["day_count"])
    payload["available_day_count"] = int(payload["available_day_count"])
    payload["completed_day_count"] = int(payload["completed_day_count"])
    payload["signal_count"] = int(payload["signal_count"])
    payload["total_pnl"] = float(payload["total_pnl"])
    payload["win_rate"] = float(payload["win_rate"])
    payload["profit_factor"] = None if payload["profit_factor"] is None else float(payload["profit_factor"])
    payload["max_drawdown"] = float(payload["max_drawdown"])
    payload["coverage_ratio"] = float(payload["coverage_ratio"])
    payload["params"] = json.loads(payload["params_json"])
    payload["strategy"] = {
        "strategy_id": payload["strategy_id"],
        "name": payload["strategy_name"],
        "template_key": payload["template_key"],
    }
    payload["day_results"] = _public_strategy_test_day_results(conn, payload["id"])
    return payload


def _public_strategy_test_day_results(conn: sqlite3.Connection, batch_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM strategy_test_day_results
        WHERE batch_id = ?
        ORDER BY trade_date DESC, id DESC
        """,
        (batch_id,),
    ).fetchall()
    results = rows_to_dicts(rows)
    for result in results:
        result["day_result_id"] = result["id"]
        result["signal_count"] = int(result["signal_count"])
        result["total_pnl"] = float(result["total_pnl"])
        result["win_rate"] = float(result["win_rate"])
        result["profit_factor"] = None if result["profit_factor"] is None else float(result["profit_factor"])
        result["closed_group_count"] = int(result["closed_group_count"])
    return results


def _public_strategy_optimization_run(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    include_candidates: bool,
) -> dict[str, Any]:
    payload = dict(row)
    payload["optimization_id"] = payload["id"]
    payload["window_trading_days"] = int(payload["window_trading_days"])
    payload["candidate_count"] = int(payload["candidate_count"])
    payload["eligible_candidate_count"] = int(payload["eligible_candidate_count"])
    payload["best_stability_score"] = (
        None if payload["best_stability_score"] is None else float(payload["best_stability_score"])
    )
    payload["search_space"] = json.loads(payload["search_space_json"])
    payload["strategy"] = {
        "strategy_id": payload["strategy_id"],
        "name": payload["strategy_name"],
        "template_key": payload["template_key"],
    }
    payload["candidates"] = _public_strategy_optimization_candidates(conn, payload["id"]) if include_candidates else []
    return payload


def _public_strategy_optimization_candidates(conn: sqlite3.Connection, optimization_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM strategy_optimization_candidates
        WHERE optimization_run_id = ?
        ORDER BY rank, id
        """,
        (optimization_id,),
    ).fetchall()
    candidates = rows_to_dicts(rows)
    for candidate in candidates:
        candidate["candidate_id"] = candidate["id"]
        candidate["rank"] = int(candidate["rank"])
        candidate["params"] = json.loads(candidate["params_json"])
        candidate["day_results"] = json.loads(candidate["day_results_json"])
        candidate["total_pnl"] = float(candidate["total_pnl"])
        candidate["win_rate"] = float(candidate["win_rate"])
        candidate["profit_factor"] = None if candidate["profit_factor"] is None else float(candidate["profit_factor"])
        candidate["max_drawdown"] = float(candidate["max_drawdown"])
        candidate["closed_group_count"] = int(candidate["closed_group_count"])
        candidate["coverage_ratio"] = float(candidate["coverage_ratio"])
        candidate["stability_score"] = float(candidate["stability_score"])
    return candidates


def _public_signals(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM strategy_signals
        WHERE run_id = ?
        ORDER BY bar_index, id
        """,
        (run_id,),
    ).fetchall()
    signals = rows_to_dicts(rows)
    for signal in signals:
        signal["signal_id"] = signal["id"]
        signal["reason_codes"] = json.loads(signal["reason_codes_json"])
        signal["metrics"] = json.loads(signal["metrics_json"])
        signal["price"] = float(signal["price"])
        signal["stop_loss_price"] = None if signal["stop_loss_price"] is None else float(signal["stop_loss_price"])
        signal["take_profit_price"] = None if signal["take_profit_price"] is None else float(signal["take_profit_price"])
    return signals


def _strategy_signal_performance(signals: list[dict[str, Any]]) -> dict[str, Any]:
    entry_groups: dict[str, dict[str, Any]] = {}
    ordered_groups: list[dict[str, Any]] = []
    ordered_signals = sorted(
        signals,
        key=lambda signal: (int(signal.get("bar_index") or 0), str(signal.get("timestamp") or ""), str(signal.get("id") or "")),
    )

    for signal in ordered_signals:
        if signal.get("action") not in {"ENTRY_LONG", "ENTRY_SHORT"}:
            continue
        signal_id = str(signal.get("signal_id") or signal.get("id"))
        group = {"entry": signal, "exits": []}
        entry_groups[signal_id] = group
        ordered_groups.append(group)

    for signal in ordered_signals:
        if signal.get("action") not in {"EXIT_LONG", "EXIT_SHORT"}:
            continue
        linked_entry_id = signal.get("linked_entry_signal_id")
        if linked_entry_id in entry_groups:
            entry_groups[linked_entry_id]["exits"].append(signal)

    total_pnl = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    closed_group_count = 0
    winning_group_count = 0
    losing_group_count = 0

    for group in ordered_groups:
        exits = group["exits"]
        if not exits:
            continue
        closed_group_count += 1
        entry = group["entry"]
        entry_price = float(entry["price"])
        side = entry["side"]
        group_pnl = 0.0
        for exit_signal in exits:
            exit_price = float(exit_signal["price"])
            exit_metrics = exit_signal.get("metrics") or {}
            exit_fraction = float(exit_metrics.get("exit_fraction") or 1.0)
            price_delta = exit_price - entry_price if side == "LONG" else entry_price - exit_price
            group_pnl += price_delta * exit_fraction
        total_pnl += group_pnl
        if group_pnl > 0:
            winning_group_count += 1
            gross_profit += group_pnl
        elif group_pnl < 0:
            losing_group_count += 1
            gross_loss += group_pnl

    win_rate = winning_group_count / closed_group_count if closed_group_count else 0.0
    profit_factor = gross_profit / abs(gross_loss) if gross_loss < 0 else None
    return {
        "unit": "price_delta_weighted_by_exit_fraction",
        "total_pnl": round(total_pnl, 6),
        "gross_profit": round(gross_profit, 6),
        "gross_loss": round(gross_loss, 6),
        "closed_group_count": closed_group_count,
        "winning_group_count": winning_group_count,
        "losing_group_count": losing_group_count,
        "win_rate": round(win_rate, 6),
        "profit_factor": None if profit_factor is None else round(profit_factor, 6),
    }


def _day_result_from_strategy_run(run: dict[str, Any]) -> dict[str, Any]:
    performance = run.get("signal_performance") or {}
    return {
        "trade_date": run["trade_date"],
        "source_archive_id": run["source_archive_id"],
        "bars_hash": run["bars_hash"],
        "strategy_run_id": run["run_id"],
        "status": run["status"],
        "failure_reason": run["failure_reason"],
        "signal_count": int(run["signal_count"]),
        "total_pnl": float(performance.get("total_pnl") or 0.0),
        "gross_profit": float(performance.get("gross_profit") or 0.0),
        "gross_loss": float(performance.get("gross_loss") or 0.0),
        "win_rate": float(performance.get("win_rate") or 0.0),
        "profit_factor": performance.get("profit_factor"),
        "closed_group_count": int(performance.get("closed_group_count") or 0),
        "winning_group_count": int(performance.get("winning_group_count") or 0),
        "losing_group_count": int(performance.get("losing_group_count") or 0),
        "indicator_hash": run["indicator_hash"],
    }


def _aggregate_day_results(
    day_results: list[dict[str, Any]],
    *,
    window_trading_days: int,
) -> dict[str, Any]:
    ordered = sorted(day_results, key=lambda day: day["trade_date"])
    completed = [day for day in ordered if day["status"] == "completed"]
    total_pnl = sum(float(day.get("total_pnl") or 0.0) for day in completed)
    gross_profit = sum(float(day.get("gross_profit") or 0.0) for day in completed)
    gross_loss = sum(float(day.get("gross_loss") or 0.0) for day in completed)
    closed_group_count = sum(int(day.get("closed_group_count") or 0) for day in completed)
    winning_group_count = sum(int(day.get("winning_group_count") or 0) for day in completed)
    signal_count = sum(int(day.get("signal_count") or 0) for day in completed)
    win_rate = winning_group_count / closed_group_count if closed_group_count else 0.0
    profit_factor = gross_profit / abs(gross_loss) if gross_loss < 0 else None
    completed_day_count = len(completed)
    available_day_count = sum(
        1 for day in ordered if day["status"] not in {"missing_archive", "non_available_archive"}
    )
    return {
        "available_day_count": available_day_count,
        "completed_day_count": completed_day_count,
        "signal_count": signal_count,
        "total_pnl": round(total_pnl, 6),
        "win_rate": round(win_rate, 6),
        "profit_factor": None if profit_factor is None else round(profit_factor, 6),
        "max_drawdown": _max_drawdown([float(day.get("total_pnl") or 0.0) for day in completed]),
        "closed_group_count": closed_group_count,
        "coverage_ratio": round(completed_day_count / window_trading_days, 6) if window_trading_days else 0.0,
    }


def _max_drawdown(day_pnls: list[float]) -> float:
    peak = 0.0
    equity = 0.0
    max_drawdown = 0.0
    for pnl in day_pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return round(max_drawdown, 6)


def _run_optimization_candidate(
    conn: sqlite3.Connection,
    *,
    strategy_id: str,
    provider: str,
    symbol: str,
    template_key: str,
    template_version: str,
    enabled: bool,
    archives: list[dict[str, Any]],
    params: dict[str, Any],
    force: bool,
) -> dict[str, Any]:
    params_hash = _params_hash(params)
    day_results: list[dict[str, Any]] = []
    for archive in archives:
        run = _run_strategy_signal_replay_with_params(
            conn,
            strategy_id=strategy_id,
            trade_date=archive["trade_date"],
            symbol=symbol,
            provider=provider,
            params=params,
            params_hash=params_hash,
            template_key=template_key,
            template_version=template_version,
            enabled=enabled,
            force=force,
        )
        day_results.append(_day_result_from_strategy_run(run))
    metrics = _aggregate_day_results(day_results, window_trading_days=len(archives) or 1)
    status = "eligible" if metrics["closed_group_count"] > 0 and metrics["completed_day_count"] > 0 else "no_signals"
    failure_reason = None
    if not enabled:
        status = "strategy_disabled"
        failure_reason = "strategy_disabled"
    elif metrics["completed_day_count"] == 0 and any(day["status"] == "failed" for day in day_results):
        status = "failed"
        failure_reason = "all_candidate_days_failed"
    elif status == "no_signals":
        failure_reason = "no_closed_strategy_signal_groups"
    stability_score = _candidate_stability_score(metrics)
    return {
        "candidate_id": new_id("stratcand"),
        "rank": 0,
        "params_json": _params_json(params),
        "params_hash": params_hash,
        "day_results_json": _json_payload(day_results),
        "status": status,
        "failure_reason": failure_reason,
        "total_pnl": metrics["total_pnl"],
        "win_rate": metrics["win_rate"],
        "profit_factor": metrics["profit_factor"],
        "max_drawdown": metrics["max_drawdown"],
        "closed_group_count": metrics["closed_group_count"],
        "coverage_ratio": metrics["coverage_ratio"],
        "stability_score": stability_score,
    }


def _candidate_stability_score(metrics: dict[str, Any]) -> float:
    profit_factor = float(metrics["profit_factor"] or 0.0)
    capped_profit_factor = min(profit_factor, 5.0)
    score = (
        float(metrics["total_pnl"])
        + float(metrics["win_rate"]) * 10.0
        + capped_profit_factor * 2.0
        + float(metrics["coverage_ratio"]) * 5.0
        - float(metrics["max_drawdown"]) * 2.0
    )
    return round(score, 6)


def _rank_optimization_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            candidate["status"] != "eligible",
            -float(candidate["stability_score"]),
            -float(candidate["total_pnl"]),
            -int(candidate["closed_group_count"]),
            candidate["params_hash"],
        ),
    )
    for index, candidate in enumerate(ranked, start=1):
        candidate["rank"] = index
    return ranked


def _validated_window_trading_days(value: int) -> int:
    window = int(value)
    if window < 1 or window > DEFAULT_STRATEGY_TEST_WINDOW_DAYS:
        raise ValueError("strategy_test_window_out_of_range")
    return window


def _recent_primary_archives(
    conn: sqlite3.Connection,
    *,
    provider: str,
    symbol: str,
    end_date: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM market_minute_archives
        WHERE provider = ? AND symbol = ? AND trade_date <= ?
        ORDER BY trade_date DESC, created_at DESC, id DESC
        LIMIT ?
        """,
        (provider, symbol.strip().upper(), end_date, limit * 3),
    ).fetchall()
    by_date: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = row_to_dict(row)
        if payload and payload["trade_date"] not in by_date:
            by_date[payload["trade_date"]] = payload
        if len(by_date) >= limit:
            break
    return sorted(by_date.values(), key=lambda row: row["trade_date"])


def _archive_scope_hash(
    conn: sqlite3.Connection,
    *,
    template_key: str,
    params: dict[str, Any],
    provider: str,
    archives: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    for archive in archives:
        context_archives = _find_strategy_context_archives(
            conn,
            template_key=template_key,
            params=params,
            provider=provider,
            trade_date=archive["trade_date"],
        )
        input_hash = _strategy_input_bars_hash(
            template_key=template_key,
            primary_archive=archive,
            context_archives=context_archives,
            params=params,
        )
        parts.append(
            "|".join(
                [
                    archive["trade_date"],
                    archive["id"],
                    archive["data_status"],
                    str(archive["bars_hash"]),
                    input_hash,
                ]
            )
        )
    return _sha256_text("\n".join(parts)) if parts else ""


def _normalize_search_space(
    search_space: dict[str, list[Any]] | None,
    *,
    enforce_candidate_cap: bool = True,
    template_key: str,
) -> dict[str, list[Any]]:
    raw_space = search_space or _default_optimization_search_space(template_key)
    schema = {param["key"]: param for param in _template_for_key(template_key)["param_schema"]}
    normalized: dict[str, list[Any]] = {}
    for key, values in raw_space.items():
        if key not in schema:
            raise ValueError(f"unsupported_strategy_optimization_param:{key}")
        if not isinstance(values, list) or not values:
            raise ValueError(f"empty_strategy_optimization_param:{key}")
        param = schema[key]
        normalized_values: list[Any] = []
        for value in values:
            if param["type"] == "integer":
                normalized_values.append(int(value))
            elif param["type"] == "number":
                normalized_values.append(round(float(value), 6))
            elif param["type"] == "enum":
                allowed = {option["value"] for option in param.get("options", [])}
                text = str(value)
                if text not in allowed:
                    raise ValueError(f"strategy_param_out_of_range:{key}")
                normalized_values.append(text)
            else:
                raise ValueError(f"unsupported_strategy_optimization_param_type:{key}")
        normalized[key] = sorted(set(normalized_values), key=lambda item: str(item))
    candidate_count = math.prod(len(values) for values in normalized.values()) if normalized else 1
    if enforce_candidate_cap and candidate_count > MAX_OPTIMIZATION_CANDIDATES:
        raise ValueError("strategy_optimization_candidate_cap_exceeded")
    return normalized


def _candidate_params_from_search_space(
    base_params: dict[str, Any],
    search_space: dict[str, list[Any]],
    *,
    allow_sampling: bool = False,
    template_key: str,
) -> list[dict[str, Any]]:
    if not search_space:
        return [_normalize_params(base_params, template_key=template_key)]
    keys = list(search_space.keys())
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    first_param_error: ValueError | None = None
    for values in itertools.product(*(search_space[key] for key in keys)):
        candidate = dict(base_params)
        candidate.update(dict(zip(keys, values, strict=True)))
        try:
            normalized = _normalize_params(candidate, template_key=template_key)
        except ValueError as exc:
            if str(exc).startswith("strategy_param_out_of_range:"):
                first_param_error = first_param_error or exc
                continue
            raise
        params_hash = _params_hash(normalized)
        if params_hash not in seen:
            seen.add(params_hash)
            candidates.append(normalized)
    if not candidates and first_param_error:
        raise first_param_error
    if len(candidates) > MAX_OPTIMIZATION_CANDIDATES and allow_sampling:
        candidates = _sample_optimization_candidates(candidates, search_space, base_params, template_key=template_key)
    if len(candidates) > MAX_OPTIMIZATION_CANDIDATES:
        raise ValueError("strategy_optimization_candidate_cap_exceeded")
    return candidates


def _sample_optimization_candidates(
    candidates: list[dict[str, Any]],
    search_space: dict[str, list[Any]],
    base_params: dict[str, Any],
    *,
    template_key: str,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_hashes: set[str] = set()

    def add(candidate: dict[str, Any]) -> None:
        if len(selected) >= MAX_OPTIMIZATION_CANDIDATES:
            return
        params_hash = _params_hash(candidate)
        if params_hash in selected_hashes:
            return
        selected_hashes.add(params_hash)
        selected.append(candidate)

    normalized_base = _normalize_params(base_params, template_key=template_key)
    base_hash = _params_hash(normalized_base)
    add(next((candidate for candidate in candidates if _params_hash(candidate) == base_hash), candidates[0]))

    for key, values in search_space.items():
        for value in values:
            match = next((candidate for candidate in candidates if candidate.get(key) == value), None)
            if match is not None:
                add(match)

    remaining = [candidate for candidate in candidates if _params_hash(candidate) not in selected_hashes]
    slots = MAX_OPTIMIZATION_CANDIDATES - len(selected)
    if slots <= 0 or not remaining:
        return selected
    if len(remaining) <= slots:
        selected.extend(remaining)
        return selected

    step = (len(remaining) - 1) / max(slots - 1, 1)
    used_indexes: set[int] = set()
    for index in range(slots):
        remaining_index = int(round(index * step))
        while remaining_index in used_indexes and remaining_index + 1 < len(remaining):
            remaining_index += 1
        while remaining_index in used_indexes and remaining_index > 0:
            remaining_index -= 1
        if remaining_index not in used_indexes:
            used_indexes.add(remaining_index)
            add(remaining[remaining_index])
    return selected


def _default_optimization_search_space(template_key: str) -> dict[str, list[Any]]:
    if template_key == BB_SQUEEZE_TEMPLATE_KEY:
        return {
            "volume_multiplier": [1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0],
            "squeeze_percentile": [3.0, 5.0, 8.0, 10.0, 12.0, 15.0, 20.0],
            "risk_reward": [1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0],
            "min_absolute_bandwidth": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0],
            "setup_minutes": [5, 8, 10, 15],
        }
    if template_key == LIQUIDITY_SWEEP_TEMPLATE_KEY:
        return {
            "local_window": [10, 15, 20, 25, 30, 40, 50],
            "shadow_ratio": [0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8],
            "volume_multiplier": [1.1, 1.2, 1.35, 1.5, 1.75, 2.0, 2.5],
            "risk_reward": [0.8, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5],
            "max_holding_bars": [2, 3, 4, 5],
        }
    if template_key == MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY:
        return {
            "adx_trend_threshold": [18.0, 20.0, 22.5, 25.0, 27.5, 30.0, 35.0],
            "adx_chop_threshold": [12.5, 15.0, 17.5, 20.0, 22.5],
            "atr_stop_multiplier": [0.9, 1.1, 1.3, 1.5, 1.8, 2.1],
            "pin_shadow_ratio": [0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7],
            "swing_lookback": [2, 3, 4, 5],
        }
    raise ValueError("unsupported_strategy_template")


def _find_strategy_test_batch_by_key(conn: sqlite3.Connection, idempotency_key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM strategy_test_batches WHERE idempotency_key = ?", (idempotency_key,)).fetchone()


def _find_strategy_optimization_by_key(conn: sqlite3.Connection, idempotency_key: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM strategy_optimization_runs WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()


def _strategy_test_idempotency_key(
    *,
    strategy_id: str,
    provider: str,
    symbol: str,
    end_date: str,
    window_trading_days: int,
    archive_scope_hash: str,
    params_hash: str,
    template_version: str,
    indicator_engine_version: str,
) -> str:
    return ":".join(
        [
            strategy_id,
            provider,
            symbol,
            end_date,
            str(window_trading_days),
            archive_scope_hash or "no_archive_scope",
            params_hash,
            template_version,
            indicator_engine_version,
        ]
    )


def _strategy_optimization_idempotency_key(
    *,
    strategy_id: str,
    provider: str,
    symbol: str,
    end_date: str,
    window_trading_days: int,
    archive_scope_hash: str,
    search_space_hash: str,
    objective: str,
    template_version: str,
    indicator_engine_version: str,
) -> str:
    return ":".join(
        [
            strategy_id,
            provider,
            symbol,
            end_date,
            str(window_trading_days),
            archive_scope_hash or "no_archive_scope",
            search_space_hash,
            objective,
            template_version,
            indicator_engine_version,
        ]
    )


def _strategy_config_row(conn: sqlite3.Connection, strategy_id: str) -> sqlite3.Row:
    ensure_default_strategy_configs(conn)
    row = conn.execute("SELECT * FROM strategy_configs WHERE id = ?", (strategy_id,)).fetchone()
    if not row:
        raise KeyError("strategy_not_found")
    return row


def _find_archive(conn: sqlite3.Connection, *, provider: str, symbol: str, trade_date: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM market_minute_archives
        WHERE provider = ? AND symbol = ? AND trade_date = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (provider, symbol, trade_date),
    ).fetchone()
    return row_to_dict(row)


def _find_strategy_context_archives(
    conn: sqlite3.Connection,
    *,
    template_key: str,
    params: dict[str, Any],
    provider: str,
    trade_date: str,
) -> dict[str, dict[str, Any]]:
    if template_key != MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY:
        return {}
    archives: dict[str, dict[str, Any]] = {}
    for symbol in _momentum_context_symbols(params):
        archive = _find_archive(conn, provider=provider, symbol=symbol, trade_date=trade_date)
        if archive:
            archives[symbol] = archive
    return archives


def _missing_context_symbols(
    template_key: str,
    params: dict[str, Any],
    context_archives: dict[str, dict[str, Any]],
) -> list[str]:
    if template_key != MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY:
        return []
    return [symbol for symbol in _momentum_context_symbols(params) if symbol not in context_archives]


def _non_available_context_archives(context_archives: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {symbol: row for symbol, row in context_archives.items() if row["data_status"] != "available"}


def _context_bars_for_template(
    template_key: str,
    context_archives: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    if template_key != MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY:
        return {}
    return {symbol: json.loads(row["bars_json"]) for symbol, row in context_archives.items()}


def _strategy_input_bars_hash(
    *,
    template_key: str,
    primary_archive: dict[str, Any] | None,
    context_archives: dict[str, dict[str, Any]],
    params: dict[str, Any],
) -> str:
    if primary_archive is None:
        return ""
    primary_hash = str(primary_archive["bars_hash"])
    if template_key != MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY:
        return primary_hash
    parts = [f"target:{primary_archive['symbol']}:{primary_archive['id']}:{primary_hash}"]
    for symbol in _momentum_context_symbols(params):
        archive = context_archives.get(symbol)
        if archive:
            parts.append(f"{symbol}:{archive['id']}:{archive['bars_hash']}:{archive['data_status']}")
        else:
            parts.append(f"{symbol}:missing")
    return _sha256_text("|".join(parts))


def _find_run_by_key(conn: sqlite3.Connection, idempotency_key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM strategy_signal_runs WHERE idempotency_key = ?", (idempotency_key,)).fetchone()


def _template_for_key(template_key: str) -> dict[str, Any]:
    for template in get_strategy_templates():
        if template["template_key"] == template_key:
            return template
    raise ValueError("unsupported_strategy_template")


def _engine_version_for_template(template_key: str) -> str:
    if template_key == BB_SQUEEZE_TEMPLATE_KEY:
        return BB_SQUEEZE_ENGINE_VERSION
    if template_key == LIQUIDITY_SWEEP_TEMPLATE_KEY:
        return LIQUIDITY_SWEEP_ENGINE_VERSION
    if template_key == MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY:
        return MOMENTUM_MEAN_REVERSION_ENGINE_VERSION
    raise ValueError("unsupported_strategy_template")


def _normalize_params(params: dict[str, Any], *, template_key: str = BB_SQUEEZE_TEMPLATE_KEY) -> dict[str, float | int | str]:
    if template_key == LIQUIDITY_SWEEP_TEMPLATE_KEY:
        return _normalize_liquidity_sweep_params(params)
    if template_key == MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY:
        return _normalize_momentum_mean_reversion_params(params)
    if template_key != BB_SQUEEZE_TEMPLATE_KEY:
        raise ValueError("unsupported_strategy_template")
    return _normalize_bb_squeeze_params(params)


def _normalize_bb_squeeze_params(params: dict[str, Any]) -> dict[str, float | int]:
    merged = {**DEFAULT_BB_SQUEEZE_PARAMS, **dict(params)}
    normalized: dict[str, float | int] = {
        "bb_period": _bounded_int(merged["bb_period"], 5, 100, "bb_period"),
        "bb_stddev": _bounded_float(merged["bb_stddev"], 0.5, 5.0, "bb_stddev"),
        "rsi_period": _bounded_int(merged["rsi_period"], 2, 100, "rsi_period"),
        "volume_average_period": _bounded_int(merged["volume_average_period"], 2, 100, "volume_average_period"),
        "volume_multiplier": _bounded_float(merged["volume_multiplier"], 1.0, 10.0, "volume_multiplier"),
        "squeeze_percentile": _bounded_float(merged["squeeze_percentile"], 1.0, 50.0, "squeeze_percentile"),
        "setup_minutes": _bounded_int(merged["setup_minutes"], 3, 60, "setup_minutes"),
        "body_strength_ratio": _bounded_float(merged["body_strength_ratio"], 0.1, 1.0, "body_strength_ratio"),
        "risk_reward": _bounded_float(merged["risk_reward"], 0.5, 10.0, "risk_reward"),
        "exit_ema_period": _bounded_int(merged["exit_ema_period"], 2, 60, "exit_ema_period"),
        "min_absolute_bandwidth": _bounded_float(merged["min_absolute_bandwidth"], 0.0, 100.0, "min_absolute_bandwidth"),
    }
    return normalized


def _normalize_liquidity_sweep_params(params: dict[str, Any]) -> dict[str, float | int | str]:
    merged = {**DEFAULT_LIQUIDITY_SWEEP_PARAMS, **dict(params)}
    exit_type = str(merged["exit_type"]).strip()
    if exit_type != "OCO_Immediate":
        raise ValueError("strategy_param_out_of_range:exit_type")
    return {
        "local_window": _bounded_int(merged["local_window"], 10, 60, "local_window"),
        "shadow_ratio": _bounded_float(merged["shadow_ratio"], 0.2, 0.95, "shadow_ratio"),
        "volume_average_period": _bounded_int(merged["volume_average_period"], 2, 100, "volume_average_period"),
        "volume_multiplier": _bounded_float(merged["volume_multiplier"], 1.0, 10.0, "volume_multiplier"),
        "bb_period": _bounded_int(merged["bb_period"], 5, 100, "bb_period"),
        "bb_stddev": _bounded_float(merged["bb_stddev"], 0.5, 5.0, "bb_stddev"),
        "risk_reward": _bounded_float(merged["risk_reward"], 0.5, 10.0, "risk_reward"),
        "tick_size": _bounded_float(merged["tick_size"], 0.0001, 1.0, "tick_size"),
        "stop_tick_offset": _bounded_int(merged["stop_tick_offset"], 1, 5, "stop_tick_offset"),
        "max_holding_bars": _bounded_int(merged["max_holding_bars"], 1, 10, "max_holding_bars"),
        "exit_type": "OCO_Immediate",
    }


def _normalize_momentum_mean_reversion_params(params: dict[str, Any]) -> dict[str, float | int | str]:
    merged = {**DEFAULT_MOMENTUM_MEAN_REVERSION_PARAMS, **dict(params)}
    momentum_context = str(merged["momentum_context"]).strip()
    if momentum_context != "QQQ_SMH":
        raise ValueError("strategy_param_out_of_range:momentum_context")
    normalized: dict[str, float | int | str] = {
        "bb_period": _bounded_int(merged["bb_period"], 5, 100, "bb_period"),
        "bb_stddev": _bounded_float(merged["bb_stddev"], 0.5, 5.0, "bb_stddev"),
        "adx_period": _bounded_int(merged["adx_period"], 2, 60, "adx_period"),
        "adx_trend_threshold": _bounded_float(merged["adx_trend_threshold"], 5.0, 80.0, "adx_trend_threshold"),
        "adx_chop_threshold": _bounded_float(merged["adx_chop_threshold"], 1.0, 60.0, "adx_chop_threshold"),
        "atr_period": _bounded_int(merged["atr_period"], 2, 60, "atr_period"),
        "atr_stop_multiplier": _bounded_float(merged["atr_stop_multiplier"], 0.1, 10.0, "atr_stop_multiplier"),
        "start_hour": _bounded_int(merged["start_hour"], 0, 23, "start_hour"),
        "start_minute": _bounded_int(merged["start_minute"], 0, 59, "start_minute"),
        "end_hour": _bounded_int(merged["end_hour"], 0, 23, "end_hour"),
        "end_minute": _bounded_int(merged["end_minute"], 0, 59, "end_minute"),
        "pin_shadow_ratio": _bounded_float(merged["pin_shadow_ratio"], 0.2, 0.95, "pin_shadow_ratio"),
        "swing_lookback": _bounded_int(merged["swing_lookback"], 1, 20, "swing_lookback"),
        "tick_size": _bounded_float(merged["tick_size"], 0.0001, 1.0, "tick_size"),
        "first_target_exit_fraction": _bounded_float(
            merged["first_target_exit_fraction"],
            0.5,
            0.75,
            "first_target_exit_fraction",
        ),
        "momentum_context": "QQQ_SMH",
    }
    if float(normalized["adx_chop_threshold"]) >= float(normalized["adx_trend_threshold"]):
        raise ValueError("strategy_param_out_of_range:adx_thresholds")

    requested_start = int(normalized["start_hour"]) * 60 + int(normalized["start_minute"])
    requested_end = int(normalized["end_hour"]) * 60 + int(normalized["end_minute"])
    start = max(requested_start, 11 * 60 + 30)
    end = min(requested_end, 13 * 60 + 30)
    if start >= end:
        raise ValueError("strategy_param_out_of_range:time_window")
    normalized["start_hour"] = start // 60
    normalized["start_minute"] = start % 60
    normalized["end_hour"] = end // 60
    normalized["end_minute"] = end % 60
    return normalized


def _momentum_context_symbols(params: dict[str, Any]) -> tuple[str, str]:
    if str(params.get("momentum_context", "QQQ_SMH")) != "QQQ_SMH":
        raise ValueError("strategy_param_out_of_range:momentum_context")
    return MOMENTUM_CONTEXT_SYMBOLS


def _bounded_int(value: Any, minimum: int, maximum: int, key: str) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_strategy_param:{key}") from exc
    if coerced < minimum or coerced > maximum:
        raise ValueError(f"strategy_param_out_of_range:{key}")
    return coerced


def _bounded_float(value: Any, minimum: float, maximum: float, key: str) -> float:
    try:
        coerced = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_strategy_param:{key}") from exc
    if coerced < minimum or coerced > maximum:
        raise ValueError(f"strategy_param_out_of_range:{key}")
    return round(coerced, 6)


def _minimum_required_bars(params: dict[str, Any], *, template_key: str = BB_SQUEEZE_TEMPLATE_KEY) -> int:
    if template_key == LIQUIDITY_SWEEP_TEMPLATE_KEY:
        return max(
            int(params["local_window"]) + 1,
            int(params["volume_average_period"]) + 1,
            int(params["bb_period"]),
            5,
        )
    if template_key == MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY:
        return max(
            int(params["bb_period"]) + 1,
            int(params["swing_lookback"]) + 1,
            int(params["atr_period"]),
            int(params["adx_period"]),
        )
    return max(
        int(params["bb_period"]),
        int(params["rsi_period"]) + 1,
        int(params["volume_average_period"]) + 1,
        int(params["exit_ema_period"]),
    ) + int(params["setup_minutes"])


def _run_idempotency_key(
    *,
    strategy_id: str,
    provider: str,
    symbol: str,
    trade_date: str,
    source_archive_id: str | None,
    bars_hash: str,
    params_hash: str,
    template_version: str,
    indicator_engine_version: str,
) -> str:
    return ":".join(
        [
            strategy_id,
            provider,
            symbol,
            trade_date,
            source_archive_id or "missing_archive",
            bars_hash or "no_bars_hash",
            params_hash,
            template_version,
            indicator_engine_version,
        ]
    )


def _params_json(params: dict[str, Any]) -> str:
    return json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _params_hash(params: dict[str, Any]) -> str:
    return _sha256_text(_params_json(params))


def _json_payload(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("strategy_name_required")
    return cleaned[:120]


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _round_value(value: Any) -> Any:
    return round(float(value), 6) if isinstance(value, (float, int)) else value


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower_index = int(math.floor(rank))
    upper_index = int(math.ceil(rank))
    if lower_index == upper_index:
        return ordered[lower_index]
    lower = ordered[lower_index] * (upper_index - rank)
    upper = ordered[upper_index] * (rank - lower_index)
    return lower + upper


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
