from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from .market_quality import archive_preference_key, archive_quality_projection
from .service import _light_trade_groups_from_fills, list_fills
from .storage import new_id, row_to_dict


TRADE_BACKTEST_CONTRACT_VERSION = "trade_backtest_contract_v5"
TRADE_BACKTEST_RULE_CATALOG_VERSION = "trade_backtest_rule_catalog_v5"
TRADE_BACKTEST_ENGINE_VERSION = "trade_backtest_engine_v4"
TRADE_BACKTEST_OPTIMIZATION_CONTRACT_VERSION = "trade_backtest_optimization_contract_v1"
TRADE_BACKTEST_OPTIMIZATION_ENGINE_VERSION = "trade_backtest_optimization_engine_v1"
TRADE_BACKTEST_OBJECTIVE_VERSION = "maximize_pnl_v1"
MAX_POSITION_QUANTITY = 200.0
DAILY_LOSS_LIMIT = 1000.0
DEFAULT_MAX_POSITION_QUANTITIES = (50, 100, 150, 200, 300, 500, 1000)
DEFAULT_DAILY_LOSS_LIMITS = (500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000)
MAX_OPTIMIZATION_CANDIDATES = 120
MAX_OPTIMIZATION_POSITION_QUANTITY = 100_000
MAX_OPTIMIZATION_DAILY_LOSS_LIMIT = 1_000_000
EPSILON = 1e-9


SCENARIO_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "scenario_key": "baseline",
        "label": "基准",
        "description": "按 committed fills 原样重放，不增加交易规则。",
        "preset_version": "trade_backtest_baseline_v1",
        "params": {},
    },
    {
        "scenario_key": "rule_a",
        "label": "规则 A · 200 股上限",
        "description": "每轮交易的实时绝对持仓不超过 200 股，平仓后恢复额度。",
        "preset_version": "trade_backtest_rule_a_v5",
        "params": {"max_live_position_quantity": 200},
    },
    {
        "scenario_key": "rule_b",
        "label": "规则 B · 每日亏损控制",
        "description": "全账户当日已实现与持仓盈亏达到 -1000 USD 后立即清仓，并停止当日开仓；不完整分钟时段隔离后继续。",
        "preset_version": "trade_backtest_rule_b_v5",
        "params": {
            "daily_loss_limit": 1000,
            "pnl_scope": "all_accounts",
            "force_exit": True,
            "block_reentry": True,
        },
    },
    {
        "scenario_key": "rule_c",
        "label": "规则 C · 组合规则",
        "description": "先限制实时持仓数量，再按限仓后的组合执行每日亏损控制；不完整分钟时段隔离后继续。",
        "preset_version": "trade_backtest_rule_c_v5",
        "params": {
            "max_live_position_quantity": 200,
            "daily_loss_limit": 1000,
            "pnl_scope": "all_accounts",
            "force_exit": True,
            "block_reentry": True,
        },
    },
)


def get_trade_backtest_presets() -> dict[str, Any]:
    return {
        "contract_version": TRADE_BACKTEST_CONTRACT_VERSION,
        "rule_catalog_version": TRADE_BACKTEST_RULE_CATALOG_VERSION,
        "engine_version": TRADE_BACKTEST_ENGINE_VERSION,
        "items": [dict(item) for item in SCENARIO_PRESETS],
    }


def get_trade_backtest_optimization_presets() -> dict[str, Any]:
    return {
        "contract_version": TRADE_BACKTEST_OPTIMIZATION_CONTRACT_VERSION,
        "optimization_engine_version": TRADE_BACKTEST_OPTIMIZATION_ENGINE_VERSION,
        "objective": {
            "objective_version": TRADE_BACKTEST_OBJECTIVE_VERSION,
            "label": "总盈亏最大",
            "description": "按总盈亏从高到低排序；平局时优先更低的持仓上限和更低的每日亏损线。",
        },
        "default_max_position_quantities": list(DEFAULT_MAX_POSITION_QUANTITIES),
        "default_daily_loss_limits": list(DEFAULT_DAILY_LOSS_LIMITS),
        "max_candidate_count": MAX_OPTIMIZATION_CANDIDATES,
        "bounds": {
            "max_position_quantity": {"min": 1, "max": MAX_OPTIMIZATION_POSITION_QUANTITY},
            "daily_loss_limit": {"min": 1, "max": MAX_OPTIMIZATION_DAILY_LOSS_LIMIT},
        },
    }


def validate_trade_backtest_range(start_date: str | None, end_date: str | None) -> None:
    for value in (start_date, end_date):
        if value is None:
            continue
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("trade_backtest_date_invalid") from exc
    if start_date and end_date and start_date > end_date:
        raise ValueError("trade_backtest_date_range_invalid")


def run_trade_backtest(
    conn: sqlite3.Connection,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    validate_trade_backtest_range(start_date, end_date)
    source = _resolve_source_scope(conn, start_date=start_date, end_date=end_date)
    archive_manifest, archive_map = _resolve_archive_scope(conn, source["closed_groups"])
    archive_scope_hash = _stable_hash(archive_manifest)
    idempotency_key = _stable_hash(
        {
            "start_date": start_date,
            "end_date": end_date,
            "rule_catalog_version": TRADE_BACKTEST_RULE_CATALOG_VERSION,
            "engine_version": TRADE_BACKTEST_ENGINE_VERSION,
            "source_fill_hash": source["source_fill_hash"],
            "archive_scope_hash": archive_scope_hash,
        }
    )
    existing = conn.execute(
        "SELECT id FROM trade_backtest_runs WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if existing:
        return get_trade_backtest(conn, existing["id"])

    scenario_results = _run_scenarios(source, archive_manifest, archive_map)
    baseline_metrics = next(
        (
            item["metrics"]
            for item in scenario_results
            if item["scenario_key"] == "baseline" and item["status"] == "completed"
        ),
        None,
    )
    if baseline_metrics:
        for item in scenario_results:
            if item["status"] == "completed":
                item["metrics"]["delta_vs_baseline"] = round(
                    float(item["metrics"]["pnl"]) - float(baseline_metrics["pnl"]),
                    6,
                )

    completed_statuses = {"completed", "no_trades"}
    completed_count = sum(item["status"] in completed_statuses for item in scenario_results)
    if completed_count == len(scenario_results):
        run_status = "completed"
        failure_reason = None
    elif completed_count > 0:
        run_status = "partial_failed"
        failure_reason = "trade_backtest_scenarios_partial_failed"
    else:
        run_status = "failed"
        failure_reason = "trade_backtest_all_scenarios_failed"

    run_id = new_id("tradebt")
    created_at = _now()
    source_manifest = {
        "artifact_id": run_id,
        "source": "deduped_committed_fills",
        "source_fill_count": source["source_fill_count"],
        "source_fill_hash": source["source_fill_hash"],
        "closed_trade_group_count": len(source["closed_groups"]),
        "open_trade_group_count": len(source["open_groups"]),
        "archive_scope_hash": archive_scope_hash,
        "archives": archive_manifest,
        "result_count": len(scenario_results),
        "created_at": created_at,
    }
    with conn:
        conn.execute(
            """
            INSERT INTO trade_backtest_runs (
                id, start_date, end_date, status, failure_reason,
                rule_catalog_version, engine_version, source_fill_count,
                source_fill_hash, source_manifest_json, archive_target_count,
                archive_scope_hash, parser_versions_json,
                field_mapper_versions_json, scenario_count, idempotency_key,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                start_date,
                end_date,
                run_status,
                failure_reason,
                TRADE_BACKTEST_RULE_CATALOG_VERSION,
                TRADE_BACKTEST_ENGINE_VERSION,
                source["source_fill_count"],
                source["source_fill_hash"],
                _json(source_manifest),
                len(archive_manifest),
                archive_scope_hash,
                _json(source["parser_versions"]),
                _json(source["field_mapper_versions"]),
                len(scenario_results),
                idempotency_key,
                created_at,
            ),
        )
        for result in scenario_results:
            result_payload = {
                "scenario_key": result["scenario_key"],
                "status": result["status"],
                "failure_reason": result["failure_reason"],
                "metrics": result["metrics"],
                "evidence": result["evidence"],
            }
            conn.execute(
                """
                INSERT INTO trade_backtest_scenario_results (
                    id, run_id, scenario_key, preset_version, params_json,
                    params_hash, status, failure_reason, metrics_json,
                    evidence_json, result_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("tradebtscn"),
                    run_id,
                    result["scenario_key"],
                    result["preset_version"],
                    _json(result["params"]),
                    _stable_hash(result["params"]),
                    result["status"],
                    result["failure_reason"],
                    _json(result["metrics"]),
                    _json(result["evidence"]),
                    _stable_hash(result_payload),
                    created_at,
                ),
            )
    return get_trade_backtest(conn, run_id)


def list_trade_backtests(
    conn: sqlite3.Connection,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    validate_trade_backtest_range(start_date, end_date)
    safe_limit = max(1, min(int(limit), 100))
    clauses: list[str] = []
    params: list[Any] = []
    if start_date is not None:
        clauses.append("start_date = ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("end_date = ?")
        params.append(end_date)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT id FROM trade_backtest_runs
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (*params, safe_limit),
    ).fetchall()
    return [get_trade_backtest(conn, row["id"]) for row in rows]


def get_trade_backtest(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    run = conn.execute("SELECT * FROM trade_backtest_runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise KeyError("trade_backtest_not_found")
    scenarios = conn.execute(
        """
        SELECT * FROM trade_backtest_scenario_results
        WHERE run_id = ?
        ORDER BY CASE scenario_key
            WHEN 'baseline' THEN 0
            WHEN 'rule_a' THEN 1
            WHEN 'rule_b' THEN 2
            WHEN 'rule_c' THEN 3
            ELSE 4 END
        """,
        (run_id,),
    ).fetchall()
    return _public_run(row_to_dict(run), [row_to_dict(row) for row in scenarios])


def run_trade_backtest_optimization(
    conn: sqlite3.Connection,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    max_position_quantities: list[int | float] | None = None,
    daily_loss_limits: list[int | float] | None = None,
    objective: str = TRADE_BACKTEST_OBJECTIVE_VERSION,
) -> dict[str, Any]:
    validate_trade_backtest_range(start_date, end_date)
    if objective != TRADE_BACKTEST_OBJECTIVE_VERSION:
        raise ValueError("trade_backtest_optimization_objective_invalid")
    position_values = _normalize_optimization_values(
        max_position_quantities if max_position_quantities is not None else list(DEFAULT_MAX_POSITION_QUANTITIES),
        field="max_position_quantities",
        maximum=MAX_OPTIMIZATION_POSITION_QUANTITY,
        require_integer=True,
    )
    loss_values = _normalize_optimization_values(
        daily_loss_limits if daily_loss_limits is not None else list(DEFAULT_DAILY_LOSS_LIMITS),
        field="daily_loss_limits",
        maximum=MAX_OPTIMIZATION_DAILY_LOSS_LIMIT,
        require_integer=False,
    )
    requested_candidate_count = len(position_values) * len(loss_values)
    if requested_candidate_count > MAX_OPTIMIZATION_CANDIDATES:
        raise ValueError("trade_backtest_optimization_candidate_cap_exceeded")

    source_run = run_trade_backtest(conn, start_date=start_date, end_date=end_date)
    parameter_space = {
        "max_position_quantities": position_values,
        "daily_loss_limits": loss_values,
    }
    parameter_space_hash = _stable_hash(parameter_space)
    idempotency_key = _stable_hash(
        {
            "start_date": start_date,
            "end_date": end_date,
            "source_trade_backtest_run_id": source_run["run_id"],
            "source_fill_hash": source_run["source_fill_hash"],
            "archive_scope_hash": source_run["archive_scope_hash"],
            "objective_version": objective,
            "optimization_engine_version": TRADE_BACKTEST_OPTIMIZATION_ENGINE_VERSION,
            "parameter_space_hash": parameter_space_hash,
        }
    )
    existing = conn.execute(
        "SELECT id FROM trade_backtest_optimization_runs WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if existing:
        return get_trade_backtest_optimization(conn, existing["id"])

    source = _resolve_source_scope(conn, start_date=start_date, end_date=end_date)
    archive_manifest, archive_map = _resolve_archive_scope(conn, source["closed_groups"])
    archive_failure = next((item for item in archive_manifest if item["status"] != "available"), None)
    incomplete_archive_targets = [
        item
        for item in archive_manifest
        if item.get("coverage_status") in {"incomplete", "ignored_incomplete"}
    ]
    cross_day = any(
        str(group["opened_at"])[:10] != str(group["closed_at"])[:10]
        for group in source["closed_groups"]
    )
    run_failure_reason: str | None = None
    if not source["closed_groups"] and not source["open_groups"]:
        run_status = "no_trades"
    elif source["open_groups"]:
        run_status = "failed"
        run_failure_reason = "trade_backtest_open_trade_group_unsupported"
    elif cross_day:
        run_status = "failed"
        run_failure_reason = "trade_backtest_cross_day_position_unsupported"
    elif archive_failure:
        run_status = "failed"
        run_failure_reason = str(archive_failure["failure_reason"])
    else:
        run_status = "completed"

    baseline_scenario = next(
        (
            item
            for item in source_run["scenarios"]
            if item["scenario_key"] == "baseline" and item["status"] == "completed"
        ),
        None,
    )
    candidates: list[dict[str, Any]] = []
    if run_status == "completed":
        for max_position_quantity in position_values:
            for daily_loss_limit in loss_values:
                params = {
                    "max_live_position_quantity": max_position_quantity,
                    "daily_loss_limit": daily_loss_limit,
                }
                params_hash = _stable_hash(params)
                try:
                    simulation = _simulate_groups(
                        source["closed_groups"],
                        archive_map,
                        apply_cap=True,
                        apply_daily_stop=True,
                        max_position_quantity=float(max_position_quantity),
                        daily_loss_limit=float(daily_loss_limit),
                        archive_coverage_complete=not incomplete_archive_targets,
                        incomplete_archive_targets=incomplete_archive_targets,
                    )
                    metrics = simulation["metrics"]
                    if baseline_scenario:
                        metrics["delta_vs_baseline"] = round(
                            float(metrics["pnl"]) - float(baseline_scenario["metrics"]["pnl"]),
                            6,
                        )
                    candidate = {
                        "id": new_id("tradebtoptcand"),
                        "status": "completed",
                        "failure_reason": None,
                        "max_position_quantity": max_position_quantity,
                        "daily_loss_limit": daily_loss_limit,
                        "params": params,
                        "params_hash": params_hash,
                        "metrics": metrics,
                        "evidence": simulation["evidence"],
                    }
                except ValueError as exc:
                    candidate = {
                        "id": new_id("tradebtoptcand"),
                        "status": "failed",
                        "failure_reason": str(exc),
                        "max_position_quantity": max_position_quantity,
                        "daily_loss_limit": daily_loss_limit,
                        "params": params,
                        "params_hash": params_hash,
                        "metrics": {},
                        "evidence": {},
                    }
                candidate["result_hash"] = _stable_hash(
                    {
                        "status": candidate["status"],
                        "failure_reason": candidate["failure_reason"],
                        "params": candidate["params"],
                        "metrics": candidate["metrics"],
                        "evidence": candidate["evidence"],
                    }
                )
                candidates.append(candidate)

        completed_candidates = [item for item in candidates if item["status"] == "completed"]
        completed_candidates.sort(
            key=lambda item: (
                -float(item["metrics"]["pnl"]),
                float(item["max_position_quantity"]),
                float(item["daily_loss_limit"]),
                item["params_hash"],
            )
        )
        for rank, candidate in enumerate(completed_candidates, start=1):
            candidate["rank"] = rank
        for candidate in candidates:
            candidate.setdefault("rank", None)
        if not completed_candidates:
            run_status = "failed"
            run_failure_reason = "trade_backtest_optimization_all_candidates_failed"
        elif len(completed_candidates) != len(candidates):
            run_status = "partial_failed"
            run_failure_reason = "trade_backtest_optimization_candidates_partial_failed"

    completed_candidate_count = sum(item["status"] == "completed" for item in candidates)
    failed_candidate_count = sum(item["status"] == "failed" for item in candidates)
    best_candidate = min(
        (item for item in candidates if item.get("rank") is not None),
        key=lambda item: int(item["rank"]),
        default=None,
    )
    run_id = new_id("tradebtopt")
    created_at = _now()
    source_manifest = {
        "artifact_id": run_id,
        "source": "deduped_committed_fills",
        "source_job_id": source_run["run_id"],
        "source_fill_count": source_run["source_fill_count"],
        "source_fill_hash": source_run["source_fill_hash"],
        "archive_target_count": source_run["archive_target_count"],
        "archive_scope_hash": source_run["archive_scope_hash"],
        "parser_versions": source_run["parser_versions"],
        "field_mapper_versions": source_run["field_mapper_versions"],
        "created_at": created_at,
    }
    candidate_manifest = {
        "job_id": run_id,
        "source_job_id": source_run["run_id"],
        "artifact_id": run_id,
        "formula_count": requested_candidate_count,
        "result_count": len(candidates),
        "candidate_result_hash": _stable_hash(
            [{"params_hash": item["params_hash"], "result_hash": item["result_hash"]} for item in candidates]
        ),
        "created_at": created_at,
    }
    with conn:
        conn.execute(
            """
            INSERT INTO trade_backtest_optimization_runs (
                id, start_date, end_date, status, failure_reason,
                source_trade_backtest_run_id, objective_version,
                optimization_engine_version, parameter_space_json,
                parameter_space_hash, requested_candidate_count,
                completed_candidate_count, failed_candidate_count,
                best_candidate_id, source_fill_count, source_fill_hash,
                archive_target_count, archive_scope_hash, source_manifest_json,
                candidate_manifest_json, parser_versions_json,
                field_mapper_versions_json, idempotency_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                start_date,
                end_date,
                run_status,
                run_failure_reason,
                source_run["run_id"],
                objective,
                TRADE_BACKTEST_OPTIMIZATION_ENGINE_VERSION,
                _json(parameter_space),
                parameter_space_hash,
                requested_candidate_count,
                completed_candidate_count,
                failed_candidate_count,
                best_candidate["id"] if best_candidate else None,
                source_run["source_fill_count"],
                source_run["source_fill_hash"],
                source_run["archive_target_count"],
                source_run["archive_scope_hash"],
                _json(source_manifest),
                _json(candidate_manifest),
                _json(source_run["parser_versions"]),
                _json(source_run["field_mapper_versions"]),
                idempotency_key,
                created_at,
            ),
        )
        for candidate in candidates:
            conn.execute(
                """
                INSERT INTO trade_backtest_optimization_candidates (
                    id, optimization_run_id, rank, status, failure_reason,
                    max_position_quantity, daily_loss_limit, params_json,
                    params_hash, metrics_json, evidence_json, result_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate["id"],
                    run_id,
                    candidate["rank"],
                    candidate["status"],
                    candidate["failure_reason"],
                    candidate["max_position_quantity"],
                    candidate["daily_loss_limit"],
                    _json(candidate["params"]),
                    candidate["params_hash"],
                    _json(candidate["metrics"]),
                    _json(candidate["evidence"]),
                    candidate["result_hash"],
                    created_at,
                ),
            )
    return get_trade_backtest_optimization(conn, run_id)


def list_trade_backtest_optimizations(
    conn: sqlite3.Connection,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    validate_trade_backtest_range(start_date, end_date)
    safe_limit = max(1, min(int(limit), 100))
    clauses: list[str] = []
    params: list[Any] = []
    if start_date is not None:
        clauses.append("start_date = ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("end_date = ?")
        params.append(end_date)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT id FROM trade_backtest_optimization_runs
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (*params, safe_limit),
    ).fetchall()
    return [get_trade_backtest_optimization(conn, row["id"]) for row in rows]


def get_trade_backtest_optimization(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    run = conn.execute(
        "SELECT * FROM trade_backtest_optimization_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if not run:
        raise KeyError("trade_backtest_optimization_not_found")
    candidates = conn.execute(
        """
        SELECT * FROM trade_backtest_optimization_candidates
        WHERE optimization_run_id = ?
        ORDER BY CASE WHEN rank IS NULL THEN 1 ELSE 0 END, rank, max_position_quantity, daily_loss_limit
        """,
        (run_id,),
    ).fetchall()
    return _public_optimization_run(row_to_dict(run), [row_to_dict(row) for row in candidates])


def _normalize_optimization_values(
    values: list[int | float],
    *,
    field: str,
    maximum: float,
    require_integer: bool,
) -> list[int | float]:
    if not values:
        raise ValueError(f"trade_backtest_optimization_{field}_empty")
    normalized: set[int | float] = set()
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"trade_backtest_optimization_{field}_invalid")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric <= 0 or numeric > maximum:
            raise ValueError(f"trade_backtest_optimization_{field}_invalid")
        if require_integer and not numeric.is_integer():
            raise ValueError(f"trade_backtest_optimization_{field}_invalid")
        normalized.add(int(numeric) if numeric.is_integer() else round(numeric, 6))
    return sorted(normalized, key=float)


def _resolve_source_scope(
    conn: sqlite3.Connection,
    *,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    fills = list_fills(conn)
    groups = _light_trade_groups_from_fills(fills)
    closed_groups = [
        group
        for group in groups
        if group["status"] == "closed"
        and _date_in_scope(str(group["closed_at"])[:10], start_date, end_date)
    ]
    open_groups = [
        group
        for group in groups
        if group["status"] == "open"
        and any(_date_in_scope(str(fill["filled_at"])[:10], start_date, end_date) for fill in group["fills"])
    ]
    participating_groups = [*closed_groups, *open_groups]
    source_fills = [fill for group in participating_groups for fill in group["fills"]]
    unique_fill_ids = {str(fill["fill_id"]) for fill in source_fills}
    fill_evidence = [
        {
            "account": fill["account_canonical"],
            "symbol": fill["symbol"],
            "side": fill["side"],
            "filled_at": fill["filled_at"],
            "quantity": float(fill["quantity"]),
            "price": float(fill["price"]),
            "parser_version": fill["parser_version"],
            "field_mapper_version": fill["field_mapper_version"],
        }
        for fill in sorted(
            source_fills,
            key=lambda item: (
                item["account_canonical"],
                item["symbol"],
                item["filled_at"],
                item["fill_id"],
                float(item["quantity"]),
            ),
        )
    ]
    return {
        "closed_groups": closed_groups,
        "open_groups": open_groups,
        "source_fill_count": len(unique_fill_ids),
        "source_fill_hash": _stable_hash(fill_evidence),
        "parser_versions": sorted({fill["parser_version"] for fill in source_fills}),
        "field_mapper_versions": sorted({fill["field_mapper_version"] for fill in source_fills}),
    }


def _resolve_archive_scope(
    conn: sqlite3.Connection,
    groups: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    fill_times: dict[tuple[str, str], list[str]] = defaultdict(list)
    for group in groups:
        target = (str(group["opened_at"])[:10], str(group["symbol"]))
        fill_times[target].extend(str(fill["filled_at"]) for fill in group["fills"])

    manifest: list[dict[str, Any]] = []
    archive_map: dict[tuple[str, str], dict[str, Any]] = {}
    for trade_date, symbol in sorted(fill_times):
        rows = conn.execute(
            """
            SELECT * FROM market_minute_archives
            WHERE trade_date = ? AND symbol = ?
            ORDER BY created_at DESC, id DESC
            """,
            (trade_date, symbol),
        ).fetchall()
        candidates = [archive_quality_projection(row_to_dict(row)) for row in rows]
        candidates.sort(key=archive_preference_key)
        selected: dict[str, Any] | None = None
        selected_coverage_issue: str | None = None
        selected_bars_applied = True
        incomplete_candidate: dict[str, Any] | None = None
        ignored_interval_candidate: dict[str, Any] | None = None
        failed_candidate: dict[str, Any] | None = None
        failure_status = "missing_archive"
        failure_reason = "trade_backtest_missing_archive"
        for candidate in candidates:
            if candidate.get("data_status") != "available":
                if candidate.get("data_status") == "partial":
                    integrity_issue = _archive_integrity_issue(candidate)
                    if integrity_issue:
                        failed_candidate = candidate
                        failure_status = "invalid_archive"
                        failure_reason = integrity_issue
                        continue
                    if ignored_interval_candidate is None:
                        ignored_interval_candidate = candidate
                    continue
                if failure_status == "missing_archive":
                    failed_candidate = candidate
                    failure_status = "non_available_archive"
                    failure_reason = str(candidate.get("failure_reason") or candidate.get("data_status"))
                continue
            integrity_issue = _archive_integrity_issue(candidate)
            if integrity_issue:
                failed_candidate = candidate
                failure_status = "invalid_archive"
                failure_reason = integrity_issue
                continue
            coverage_issue = _archive_coverage_issue(candidate, fill_times[(trade_date, symbol)])
            if coverage_issue:
                if coverage_issue == "trade_backtest_archive_fill_window_not_covered":
                    if incomplete_candidate is None:
                        incomplete_candidate = candidate
                    continue
                failed_candidate = candidate
                failure_status = "invalid_archive"
                failure_reason = coverage_issue
                continue
            selected = candidate
            break

        if selected is None and incomplete_candidate is not None:
            selected = incomplete_candidate
            selected_coverage_issue = "trade_backtest_archive_fill_window_not_covered"
        if selected is None and ignored_interval_candidate is not None:
            selected = ignored_interval_candidate
            selected_coverage_issue = str(
                ignored_interval_candidate.get("failure_reason") or "trade_backtest_archive_partial_interval"
            )
            selected_bars_applied = False

        if selected:
            if selected_bars_applied:
                archive_map[(trade_date, symbol)] = selected
            manifest.append(
                {
                    "trade_date": trade_date,
                    "symbol": symbol,
                    "status": "available",
                    "failure_reason": None,
                    "coverage_status": (
                        "complete" if selected_coverage_issue is None
                        else "incomplete" if selected_bars_applied
                        else "ignored_incomplete"
                    ),
                    "coverage_reason": selected_coverage_issue,
                    "bars_applied": selected_bars_applied,
                    "archive_id": selected["id"],
                    "provider": selected["provider"],
                    "bars_hash": selected["bars_hash"],
                    "bar_count": int(selected["bar_count"]),
                }
            )
        else:
            manifest.append(
                {
                    "trade_date": trade_date,
                    "symbol": symbol,
                    "status": failure_status,
                    "failure_reason": failure_reason,
                    "coverage_status": "unavailable",
                    "coverage_reason": None,
                    "bars_applied": False,
                    "archive_id": None if failed_candidate is None else failed_candidate.get("id"),
                    "provider": None if failed_candidate is None else failed_candidate.get("provider"),
                    "bars_hash": None if failed_candidate is None else failed_candidate.get("bars_hash"),
                    "bar_count": 0 if failed_candidate is None else int(failed_candidate.get("bar_count") or 0),
                }
            )
    return manifest, archive_map


def _archive_integrity_issue(archive: dict[str, Any]) -> str | None:
    try:
        bars = json.loads(str(archive.get("bars_json") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return "trade_backtest_archive_json_invalid"
    if not isinstance(bars, list) or not bars:
        return "trade_backtest_archive_empty"
    if len(bars) != int(archive.get("bar_count") or 0):
        return "trade_backtest_archive_bar_count_mismatch"
    actual_hash = hashlib.sha256(str(archive["bars_json"]).encode("utf-8")).hexdigest()
    if actual_hash != archive.get("bars_hash"):
        return "trade_backtest_archive_hash_mismatch"
    archive["bars"] = bars
    return None


def _archive_coverage_issue(archive: dict[str, Any], fill_times: list[str]) -> str | None:
    bar_minutes = sorted(
        minute
        for minute in (_minute_key(str(bar.get("timestamp") or "")) for bar in archive.get("bars", []))
        if minute is not None
    )
    target_minutes = sorted(minute for minute in (_minute_key(value) for value in fill_times) if minute is not None)
    if not bar_minutes or len(target_minutes) != len(fill_times):
        return "trade_backtest_archive_timestamp_invalid"
    if bar_minutes[0] > target_minutes[0] or bar_minutes[-1] < target_minutes[-1]:
        return "trade_backtest_archive_fill_window_not_covered"
    return None


def _run_scenarios(
    source: dict[str, Any],
    archive_manifest: list[dict[str, Any]],
    archive_map: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    groups = source["closed_groups"]
    if not groups and not source["open_groups"]:
        return [_scenario_result(preset, status="no_trades") for preset in SCENARIO_PRESETS]

    archive_failure = next((item for item in archive_manifest if item["status"] != "available"), None)
    incomplete_archive_targets = [
        item
        for item in archive_manifest
        if item.get("coverage_status") in {"incomplete", "ignored_incomplete"}
    ]
    cross_day = any(str(group["opened_at"])[:10] != str(group["closed_at"])[:10] for group in groups)
    if source["open_groups"]:
        return [
            _scenario_result(
                preset,
                status="open_trade_group",
                failure_reason="trade_backtest_open_trade_group_unsupported",
            )
            for preset in SCENARIO_PRESETS
        ]
    if cross_day:
        return [
            _scenario_result(
                preset,
                status="unsupported_cross_day_position",
                failure_reason="trade_backtest_cross_day_position_unsupported",
            )
            for preset in SCENARIO_PRESETS
        ]

    results: list[dict[str, Any]] = []
    for preset in SCENARIO_PRESETS:
        scenario_key = preset["scenario_key"]
        requires_stop_evidence = scenario_key in {"rule_b", "rule_c"}
        if requires_stop_evidence and archive_failure:
            results.append(
                _scenario_result(
                    preset,
                    status=str(archive_failure["status"]),
                    failure_reason=str(archive_failure["failure_reason"]),
                    evidence={"failed_archive_target": archive_failure},
                )
            )
            continue
        try:
            simulation = _simulate_groups(
                groups,
                archive_map,
                apply_cap=scenario_key in {"rule_a", "rule_c"},
                apply_daily_stop=scenario_key in {"rule_b", "rule_c"},
                max_position_quantity=float(preset["params"].get("max_live_position_quantity", MAX_POSITION_QUANTITY)),
                daily_loss_limit=float(preset["params"].get("daily_loss_limit", DAILY_LOSS_LIMIT)),
                archive_coverage_complete=archive_failure is None and not incomplete_archive_targets,
                incomplete_archive_targets=incomplete_archive_targets,
            )
        except ValueError as exc:
            results.append(_scenario_result(preset, status="failed", failure_reason=str(exc)))
            continue
        results.append(
            _scenario_result(
                preset,
                status="completed",
                metrics=simulation["metrics"],
                evidence=simulation["evidence"],
            )
        )
    return results


def _simulate_groups(
    groups: list[dict[str, Any]],
    archive_map: dict[tuple[str, str], dict[str, Any]],
    *,
    apply_cap: bool,
    apply_daily_stop: bool,
    max_position_quantity: float,
    daily_loss_limit: float,
    archive_coverage_complete: bool,
    incomplete_archive_targets: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped_by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for group in groups:
        trade_date = str(group["closed_at"])[:10]
        grouped_by_day[trade_date].append(group)

    completed_groups: list[dict[str, Any]] = []
    capped_open_quantity = 0.0
    forced_exit_count = 0
    stop_trigger_days = 0
    blocked_open_quantity = 0.0
    blocked_trade_groups: set[str] = set()
    overall_worst = 0.0

    for trade_date in sorted(grouped_by_day):
        day_groups = grouped_by_day[trade_date]
        fill_events: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        for group in day_groups:
            for fill in group["fills"]:
                minute = _minute_key(str(fill["filled_at"]))
                if minute is None:
                    raise ValueError("trade_backtest_fill_timestamp_invalid")
                fill_events[minute].append((group, fill))
        for events in fill_events.values():
            events.sort(key=lambda item: (item[1]["filled_at"], item[1]["fill_id"]))

        bars_by_minute: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for group in day_groups:
            archive = archive_map.get((trade_date, group["symbol"]))
            if not archive:
                continue
            for bar in archive.get("bars", []):
                minute = _minute_key(str(bar.get("timestamp") or ""))
                if minute:
                    bars_by_minute[minute][group["symbol"]] = bar

        minute_keys = sorted(set(fill_events) | set(bars_by_minute))
        if fill_events:
            first_fill_minute = min(fill_events)
            last_fill_minute = max(fill_events)
            minute_keys = [minute for minute in minute_keys if first_fill_minute <= minute <= last_fill_minute]

        states: dict[str, dict[str, Any]] = {}
        day_realized = 0.0
        day_worst = 0.0
        stopped = False

        for minute in minute_keys:
            minute_bars = bars_by_minute.get(minute, {})
            fill_group_ids = {group["trade_group_id"] for group, _fill in fill_events.get(minute, [])}

            if not stopped and states:
                for group_id, state in states.items():
                    bar = minute_bars.get(state["symbol"])
                    if bar and group_id not in fill_group_ids and state["eligible_from_minute"] <= minute:
                        state["mark"] = float(bar["open"])
                equity_at_open = _portfolio_equity(day_realized, states)
                day_worst = min(day_worst, equity_at_open)
                if apply_daily_stop and equity_at_open <= -daily_loss_limit + EPSILON:
                    forced, realized = _force_close_states(states)
                    completed_groups.extend(forced)
                    forced_exit_count += len(forced)
                    day_realized += realized
                    stop_trigger_days += 1
                    stopped = True

            if not stopped and states:
                adverse_marks: dict[str, float] = {}
                for group_id, state in states.items():
                    bar = minute_bars.get(state["symbol"])
                    if not bar or group_id in fill_group_ids or state["eligible_from_minute"] > minute:
                        continue
                    adverse_marks[group_id] = float(bar["low"] if state["direction_sign"] > 0 else bar["high"])
                if adverse_marks:
                    equity_at_open = _portfolio_equity(day_realized, states)
                    equity_at_adverse = _portfolio_equity(day_realized, states, adverse_marks)
                    if apply_daily_stop and equity_at_adverse <= -daily_loss_limit + EPSILON:
                        if equity_at_open <= -daily_loss_limit + EPSILON:
                            fraction = 0.0
                        else:
                            denominator = equity_at_adverse - equity_at_open
                            fraction = 1.0 if abs(denominator) < EPSILON else (-daily_loss_limit - equity_at_open) / denominator
                            fraction = max(0.0, min(1.0, fraction))
                        for group_id, adverse in adverse_marks.items():
                            state = states[group_id]
                            state["mark"] = float(state["mark"]) + fraction * (adverse - float(state["mark"]))
                        forced, realized = _force_close_states(states)
                        completed_groups.extend(forced)
                        forced_exit_count += len(forced)
                        day_realized += realized
                        day_worst = min(day_worst, -daily_loss_limit)
                        stop_trigger_days += 1
                        stopped = True
                    else:
                        day_worst = min(day_worst, equity_at_adverse)
                        for group_id in adverse_marks:
                            state = states[group_id]
                            state["mark"] = float(minute_bars[state["symbol"]]["close"])
                        day_worst = min(day_worst, _portfolio_equity(day_realized, states))

            for group, fill in fill_events.get(minute, []):
                entry_side = "BUY" if group["direction"] == "LONG" else "SELL"
                if stopped:
                    if fill["side"] == entry_side:
                        blocked_open_quantity += float(fill["quantity"])
                        blocked_trade_groups.add(group["trade_group_id"])
                    continue

                group_id = group["trade_group_id"]
                state = states.get(group_id)
                if fill["side"] == entry_side:
                    current_quantity = 0.0 if state is None else abs(float(state["position"]))
                    capacity = float("inf") if not apply_cap else max(0.0, max_position_quantity - current_quantity)
                    accepted = min(float(fill["quantity"]), capacity)
                    capped_open_quantity += max(0.0, float(fill["quantity"]) - accepted)
                    if accepted > EPSILON:
                        if state is None:
                            state = _new_simulation_state(group)
                            states[group_id] = state
                        _apply_simulated_fill(state, fill["side"], accepted, float(fill["price"]), is_entry=True)
                        state["eligible_from_minute"] = _next_minute(minute)
                elif state is not None:
                    accepted = min(float(fill["quantity"]), abs(float(state["position"])))
                    if accepted > EPSILON:
                        _apply_simulated_fill(state, fill["side"], accepted, float(fill["price"]), is_entry=False)
                        state["eligible_from_minute"] = _next_minute(minute)
                        if abs(float(state["position"])) <= EPSILON:
                            result = _complete_state(state, forced=False)
                            completed_groups.append(result)
                            day_realized += float(result["pnl"])
                            states.pop(group_id, None)

                day_equity = _portfolio_equity(day_realized, states)
                day_worst = min(day_worst, day_equity)
                if apply_daily_stop and day_equity <= -daily_loss_limit + EPSILON:
                    forced, realized = _force_close_states(states)
                    completed_groups.extend(forced)
                    forced_exit_count += len(forced)
                    day_realized += realized
                    stop_trigger_days += 1
                    stopped = True

        if states:
            raise ValueError("trade_backtest_simulation_left_open_position")
        overall_worst = min(overall_worst, day_worst)

    metrics = _summary_metrics(
        completed_groups,
        worst_intraday_pnl=overall_worst if archive_coverage_complete else None,
        capped_open_quantity=capped_open_quantity,
        forced_exit_count=forced_exit_count,
        stop_trigger_days=stop_trigger_days,
        blocked_open_quantity=blocked_open_quantity,
        blocked_open_trade_count=len(blocked_trade_groups),
        ignored_incomplete_archive_target_count=len(incomplete_archive_targets),
    )
    evidence = {
        "source_trade_group_count": len(groups),
        "result_trade_group_count": len(completed_groups),
        "archive_coverage_complete": archive_coverage_complete,
        "ignored_incomplete_archive_target_count": len(incomplete_archive_targets),
        "ignored_incomplete_archive_targets": incomplete_archive_targets,
        "capped_open_quantity": _round_quantity(capped_open_quantity),
        "forced_exit_count": forced_exit_count,
        "stop_trigger_days": stop_trigger_days,
        "blocked_open_quantity": _round_quantity(blocked_open_quantity),
        "blocked_open_trade_count": len(blocked_trade_groups),
        "max_position_quantity": _round_quantity(max_position_quantity) if apply_cap else None,
        "daily_loss_limit": round(daily_loss_limit, 6) if apply_daily_stop else None,
    }
    evidence["event_hash"] = _stable_hash(evidence)
    return {"metrics": metrics, "evidence": evidence}


def _new_simulation_state(group: dict[str, Any]) -> dict[str, Any]:
    direction_sign = 1.0 if group["direction"] == "LONG" else -1.0
    return {
        "trade_group_id": group["trade_group_id"],
        "trade_date": str(group["closed_at"])[:10],
        "symbol": group["symbol"],
        "direction_sign": direction_sign,
        "position": 0.0,
        "cash": 0.0,
        "mark": 0.0,
        "entry_quantity": 0.0,
        "exit_quantity": 0.0,
        "eligible_from_minute": "9999-12-31T23:59",
    }


def _apply_simulated_fill(
    state: dict[str, Any],
    side: str,
    quantity: float,
    price: float,
    *,
    is_entry: bool,
) -> None:
    side_sign = 1.0 if side == "BUY" else -1.0
    state["position"] = float(state["position"]) + side_sign * quantity
    state["cash"] = float(state["cash"]) + (-quantity * price if side_sign > 0 else quantity * price)
    state["mark"] = price
    if is_entry:
        state["entry_quantity"] = float(state["entry_quantity"]) + quantity
    else:
        state["exit_quantity"] = float(state["exit_quantity"]) + quantity


def _portfolio_equity(
    realized: float,
    states: dict[str, dict[str, Any]],
    mark_overrides: dict[str, float] | None = None,
) -> float:
    equity = realized
    for group_id, state in states.items():
        mark = float((mark_overrides or {}).get(group_id, state["mark"]))
        equity += float(state["cash"]) + float(state["position"]) * mark
    return equity


def _force_close_states(states: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
    results: list[dict[str, Any]] = []
    realized = 0.0
    for state in list(states.values()):
        quantity = abs(float(state["position"]))
        if quantity <= EPSILON:
            continue
        side = "SELL" if float(state["position"]) > 0 else "BUY"
        _apply_simulated_fill(state, side, quantity, float(state["mark"]), is_entry=False)
        result = _complete_state(state, forced=True)
        results.append(result)
        realized += float(result["pnl"])
    states.clear()
    return results, realized


def _complete_state(state: dict[str, Any], *, forced: bool) -> dict[str, Any]:
    return {
        "trade_group_id": state["trade_group_id"],
        "trade_date": state["trade_date"],
        "symbol": state["symbol"],
        "pnl": round(float(state["cash"]), 6),
        "traded_quantity": _round_quantity(min(float(state["entry_quantity"]), float(state["exit_quantity"]))),
        "forced": forced,
    }


def _summary_metrics(
    completed_groups: list[dict[str, Any]],
    *,
    worst_intraday_pnl: float | None,
    capped_open_quantity: float,
    forced_exit_count: int,
    stop_trigger_days: int,
    blocked_open_quantity: float,
    blocked_open_trade_count: int,
    ignored_incomplete_archive_target_count: int,
) -> dict[str, Any]:
    pnls = [float(item["pnl"]) for item in completed_groups]
    wins = [value for value in pnls if value > EPSILON]
    losses = [value for value in pnls if value < -EPSILON]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    traded_quantity = sum(float(item["traded_quantity"]) for item in completed_groups)
    win_rate = len(wins) / len(pnls) if pnls else 0.0
    loss_rate = len(losses) / len(pnls) if pnls else 0.0
    average_profit = gross_profit / len(wins) if wins else 0.0
    average_loss = gross_loss / len(losses) if losses else 0.0
    expected_value = None if not pnls else win_rate * average_profit - loss_rate * average_loss
    pnl = sum(pnls)
    return {
        "pnl": round(pnl, 6),
        "delta_vs_baseline": 0.0,
        "closed_trade_count": len(completed_groups),
        "traded_quantity": _round_quantity(traded_quantity),
        "win_rate": round(win_rate, 6),
        "profit_factor": None if gross_loss <= EPSILON else round(gross_profit / gross_loss, 6),
        "expected_value_per_trade": None if expected_value is None else round(expected_value, 6),
        "net_profit_per_share": None if traded_quantity <= EPSILON else round(pnl / traded_quantity, 6),
        "worst_intraday_pnl": None if worst_intraday_pnl is None else round(worst_intraday_pnl, 6),
        "capped_open_quantity": _round_quantity(capped_open_quantity),
        "forced_exit_count": forced_exit_count,
        "stop_trigger_days": stop_trigger_days,
        "blocked_open_quantity": _round_quantity(blocked_open_quantity),
        "blocked_open_trade_count": blocked_open_trade_count,
        "ignored_incomplete_archive_target_count": ignored_incomplete_archive_target_count,
    }


def _scenario_result(
    preset: dict[str, Any],
    *,
    status: str,
    failure_reason: str | None = None,
    metrics: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **preset,
        "status": status,
        "failure_reason": failure_reason,
        "metrics": metrics or {},
        "evidence": evidence or {},
    }


def _public_run(run: dict[str, Any], scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    preset_by_key = {item["scenario_key"]: item for item in SCENARIO_PRESETS}
    return {
        "id": run["id"],
        "run_id": run["id"],
        "contract_version": TRADE_BACKTEST_CONTRACT_VERSION,
        "start_date": run["start_date"],
        "end_date": run["end_date"],
        "status": run["status"],
        "failure_reason": run["failure_reason"],
        "rule_catalog_version": run["rule_catalog_version"],
        "engine_version": run["engine_version"],
        "source_fill_count": int(run["source_fill_count"]),
        "source_fill_hash": run["source_fill_hash"],
        "archive_target_count": int(run["archive_target_count"]),
        "archive_scope_hash": run["archive_scope_hash"],
        "parser_versions": json.loads(run["parser_versions_json"]),
        "field_mapper_versions": json.loads(run["field_mapper_versions_json"]),
        "scenario_count": int(run["scenario_count"]),
        "idempotency_key": run["idempotency_key"],
        "created_at": run["created_at"],
        "scenarios": [
            {
                "scenario_key": item["scenario_key"],
                "label": preset_by_key[item["scenario_key"]]["label"],
                "description": preset_by_key[item["scenario_key"]]["description"],
                "preset_version": item["preset_version"],
                "params": json.loads(item["params_json"]),
                "status": item["status"],
                "failure_reason": item["failure_reason"],
                "metrics": json.loads(item["metrics_json"]),
                "evidence": json.loads(item["evidence_json"]),
                "result_hash": item["result_hash"],
            }
            for item in scenarios
        ],
    }


def _public_optimization_run(run: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    completed_count = max(1, int(run["completed_candidate_count"]))
    public_candidates: list[dict[str, Any]] = []
    for item in candidates:
        rank = int(item["rank"]) if item["rank"] is not None else None
        if rank == 1:
            tone = "best"
        elif rank is not None and rank <= max(1, math.ceil(completed_count * 0.25)):
            tone = "strong"
        elif rank is not None and rank > math.ceil(completed_count * 0.75):
            tone = "weak"
        else:
            tone = "neutral"
        public_candidates.append(
            {
                "id": item["id"],
                "candidate_id": item["id"],
                "rank": rank,
                "tone": tone,
                "status": item["status"],
                "failure_reason": item["failure_reason"],
                "max_position_quantity": _round_quantity(float(item["max_position_quantity"])),
                "daily_loss_limit": _round_quantity(float(item["daily_loss_limit"])),
                "params": json.loads(item["params_json"]),
                "params_hash": item["params_hash"],
                "metrics": json.loads(item["metrics_json"]),
                "evidence": json.loads(item["evidence_json"]),
                "result_hash": item["result_hash"],
            }
        )
    best_candidate = next((item for item in public_candidates if item["id"] == run["best_candidate_id"]), None)
    parameter_space = json.loads(run["parameter_space_json"])
    matrix = [
        {
            "daily_loss_limit": daily_loss_limit,
            "cells": [
                next(
                    (
                        item
                        for item in public_candidates
                        if float(item["max_position_quantity"]) == float(max_position_quantity)
                        and float(item["daily_loss_limit"]) == float(daily_loss_limit)
                    ),
                    None,
                )
                for max_position_quantity in parameter_space["max_position_quantities"]
            ],
        }
        for daily_loss_limit in parameter_space["daily_loss_limits"]
    ]
    return {
        "id": run["id"],
        "run_id": run["id"],
        "job_id": run["id"],
        "current_batch_id": run["id"],
        "artifact_id": run["id"],
        "source_job_id": run["source_trade_backtest_run_id"],
        "source_trade_backtest_run_id": run["source_trade_backtest_run_id"],
        "contract_version": TRADE_BACKTEST_OPTIMIZATION_CONTRACT_VERSION,
        "start_date": run["start_date"],
        "end_date": run["end_date"],
        "status": run["status"],
        "failure_reason": run["failure_reason"],
        "objective_version": run["objective_version"],
        "optimization_engine_version": run["optimization_engine_version"],
        "parameter_space": parameter_space,
        "parameter_space_hash": run["parameter_space_hash"],
        "requested_candidate_count": int(run["requested_candidate_count"]),
        "total_candidates": int(run["requested_candidate_count"]),
        "returned_candidate_count": len(public_candidates),
        "completed_candidate_count": int(run["completed_candidate_count"]),
        "failed_candidate_count": int(run["failed_candidate_count"]),
        "source_fill_count": int(run["source_fill_count"]),
        "source_fill_hash": run["source_fill_hash"],
        "archive_target_count": int(run["archive_target_count"]),
        "archive_scope_hash": run["archive_scope_hash"],
        "source_manifest": json.loads(run["source_manifest_json"]),
        "candidate_manifest": json.loads(run["candidate_manifest_json"]),
        "parser_versions": json.loads(run["parser_versions_json"]),
        "field_mapper_versions": json.loads(run["field_mapper_versions_json"]),
        "idempotency_key": run["idempotency_key"],
        "created_at": run["created_at"],
        "is_preview": False,
        "source_reason": "exact_scope_latest_complete_ledger",
        "best_candidate": best_candidate,
        "top_candidates": [item for item in public_candidates if item["rank"] is not None][:10],
        "matrix": matrix,
        "candidates": public_candidates,
    }


def _date_in_scope(value: str, start_date: str | None, end_date: str | None) -> bool:
    return (start_date is None or value >= start_date) and (end_date is None or value <= end_date)


def _minute_key(value: str) -> str | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed.replace(second=0, microsecond=0).isoformat(timespec="minutes")


def _next_minute(value: str) -> str:
    return (datetime.fromisoformat(value) + timedelta(minutes=1)).isoformat(timespec="minutes")


def _round_quantity(value: float) -> int | float:
    return int(round(value)) if abs(value - round(value)) <= EPSILON else round(value, 6)


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
