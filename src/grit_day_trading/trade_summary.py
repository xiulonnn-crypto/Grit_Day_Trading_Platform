from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .service import (
    TRADE_EVALUATION_MODEL_VERSION,
    _clock_minute,
    _light_trade_groups,
    _public_trade_review,
    _trade_evaluation_factors,
    _trade_group_path_drawdown,
)
from .storage import new_id, row_to_dict


TRADE_SUMMARY_CONTRACT_VERSION = "trade_summary_contract_v3"
TRADE_SUMMARY_RULE_CATALOG_VERSION = "intraday_review_rule_catalog_v2"
TRADE_SUMMARY_PROMPT_VERSION = "trade_summary_prompt_v3"
TRADE_SUMMARY_PROVIDER = "openai_compatible_local"
TRADE_SUMMARY_SESSION_PROVIDER = "codex_session"
TRADE_SUMMARY_MIN_CLOSED_TRADES = 20
TRADE_SUMMARY_MIN_WINS = 5
TRADE_SUMMARY_MIN_LOSSES = 5
TRADE_SUMMARY_MIN_RULE_EVIDENCE = 3
TRADE_SUMMARY_WIN_SUPPORT_THRESHOLD = 0.70
TRADE_SUMMARY_LOSS_WEAKNESS_THRESHOLD = 0.40

TRADE_SUMMARY_SOURCES = [
    {
        "id": "opening_range_breakout",
        "title": "Opening Range Breakout 研究",
        "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284",
        "kind": "research",
    },
    {
        "id": "market_intraday_momentum",
        "title": "Market Intraday Momentum",
        "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866",
        "kind": "research",
    },
    {
        "id": "short_term_reversal_liquidity",
        "title": "NBER 短期反转与流动性研究",
        "url": "https://www.nber.org/papers/w30917",
        "kind": "research",
    },
    {
        "id": "sec_day_trading_risk",
        "title": "SEC 日内交易说明",
        "url": "https://www.sec.gov/about/reports-publications/investorpubsdaytipshtm",
        "kind": "risk",
    },
]

TRADE_SUMMARY_RULE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "catalog_order": 1,
        "family": "价格行为",
        "execute_rule_id": "execute_breakout_retest_confirmation",
        "avoid_rule_id": "avoid_unconfirmed_breakout_entry",
        "execute_title": "等待突破与回踩确认后再执行",
        "avoid_title": "规避无确认追突破",
        "execute_condition": "突破 K 收盘站在关键位外后，等待 1–2 根 1 分钟 K 回踩；回踩不重新收回区间且确认 K 同向收盘才入场。",
        "avoid_condition": "突破后 2 根 1 分钟 K 内没有回踩确认，或确认 K 收回原区间，取消本次入场，不追价。",
        "execute_steps": (
            ("确认窗口", "突破后 1–2 根 1 分钟 K"),
            ("入场触发", "回踩守住关键位，确认 K 同向收盘"),
            ("取消条件", "任一确认 K 收盘重新进入原区间"),
        ),
        "avoid_steps": (
            ("禁止追价", "突破后未回踩，不直接市价追入"),
            ("最长等待", "超过 2 根 1 分钟 K 仍未确认即放弃"),
            ("失效条件", "确认 K 收盘回到原区间"),
        ),
        "factor_names": ("momentum_alignment", "mfe_mae"),
        "review_reason_codes": ("chased_breakout", "weak_confirmation", "poor_location"),
        "source_ids": ("opening_range_breakout", "short_term_reversal_liquidity"),
    },
    {
        "catalog_order": 2,
        "family": "趋势一致性",
        "execute_rule_id": "execute_vwap_trend_alignment",
        "avoid_rule_id": "avoid_against_vwap_context",
        "execute_title": "只执行 VWAP 与趋势方向一致的机会",
        "avoid_title": "规避逆 VWAP 与主趋势入场",
        "execute_condition": "多单只在价格收于 VWAP 上方且 20 EMA 上行时执行，空单条件相反；入场价距 VWAP 不超过 1.0 ATR。",
        "avoid_condition": "方向与 VWAP 或 20 EMA 斜率冲突，或入场价距 VWAP 超过 1.0 ATR 时，跳过交易。",
        "execute_steps": (
            ("多单条件", "收盘在 VWAP 上方且 20 EMA 上行"),
            ("空单条件", "收盘在 VWAP 下方且 20 EMA 下行"),
            ("追价上限", "入场价距 VWAP ≤ 1.0 ATR"),
        ),
        "avoid_steps": (
            ("方向冲突", "VWAP 位置与 20 EMA 斜率不一致即等待"),
            ("距离上限", "距 VWAP > 1.0 ATR 不入场"),
            ("恢复条件", "等待价格回到 1.0 ATR 内并重新同向收盘"),
        ),
        "factor_names": ("vwap_execution", "momentum_alignment"),
        "review_reason_codes": ("against_context", "poor_location"),
        "source_ids": ("market_intraday_momentum",),
    },
    {
        "catalog_order": 3,
        "family": "量价确认",
        "execute_rule_id": "execute_volume_confirmed_breakout",
        "avoid_rule_id": "avoid_low_volume_breakout",
        "execute_title": "突破必须获得量能确认",
        "avoid_title": "规避低量能突破",
        "execute_condition": "突破 K 成交量至少达到前 20 根 1 分钟 K 均量的 1.5 倍，且后续 2 根 K 中至少 1 根继续高于均量。",
        "avoid_condition": "突破 K 成交量低于前 20 根均量的 1.2 倍时直接跳过；介于 1.2–1.5 倍只观察，不入场。",
        "execute_steps": (
            ("突破量能", "≥ 前 20 根均量的 1.5 倍"),
            ("延续确认", "后续 2 根 K 至少 1 根成交量 > 均量"),
            ("入场时限", "量能确认后下一根 K 内完成入场"),
        ),
        "avoid_steps": (
            ("直接跳过", "突破量能 < 前 20 根均量的 1.2 倍"),
            ("仅观察", "量能处于 1.2–1.5 倍"),
            ("取消条件", "后续 2 根 K 均低于均量"),
        ),
        "factor_names": ("volume_confirmation", "momentum_alignment"),
        "review_reason_codes": ("weak_confirmation",),
        "source_ids": ("opening_range_breakout", "market_intraday_momentum"),
    },
    {
        "catalog_order": 4,
        "family": "风险退出",
        "execute_rule_id": "execute_structural_and_time_stop",
        "avoid_rule_id": "avoid_delayed_stop_or_exit",
        "execute_title": "结构失效后立即执行止损或时间止损",
        "avoid_title": "规避拖延止损与忽略退出信号",
        "execute_condition": "初始止损放在结构失效位且单笔风险不超过复盘本金的 0.5%；入场后 5 根 1 分钟 K 未达到 +0.5R，执行时间止损。",
        "avoid_condition": "浮亏达到 -1R、结构失效或 5 根 1 分钟 K 未推进时必须退出，不扩大止损、不补仓摊平。",
        "execute_steps": (
            ("单笔风险", "≤ 复盘本金的 0.5%"),
            ("硬止损", "结构失效位或 -1R，取更近者"),
            ("时间止损", "5 根 1 分钟 K 未达到 +0.5R 即退出"),
        ),
        "avoid_steps": (
            ("强制退出", "触及 -1R 或结构失效立即平仓"),
            ("禁止动作", "不得扩大止损或补仓摊平"),
            ("无进展退出", "5 根 1 分钟 K 未达到 +0.5R"),
        ),
        "factor_names": ("mfe_mae", "exit_efficiency"),
        "review_reason_codes": ("stop_too_late", "exit_signal_ignored", "exit_plan_unclear"),
        "source_ids": ("short_term_reversal_liquidity", "sec_day_trading_risk"),
    },
    {
        "catalog_order": 5,
        "family": "盈利保护",
        "execute_rule_id": "execute_scale_and_trail_profit",
        "avoid_rule_id": "avoid_profit_giveback",
        "execute_title": "分批止盈并移动保护剩余仓位",
        "avoid_title": "规避盈利大幅回吐",
        "execute_condition": "达到 +1R 时止盈 50%，剩余仓位止损移到入场价；达到 +2R 再止盈 25%，最后 25% 用 9 EMA 收盘破位或前两根 K 高低点跟踪。",
        "avoid_condition": "达到 +1R 后未止盈至少 50% 或未移动保护视为违规；剩余仓位从峰值回撤 0.5R 时退出。",
        "execute_steps": (
            ("第一目标", "+1R 止盈 50%，止损移到入场价"),
            ("第二目标", "+2R 再止盈 25%"),
            ("尾仓管理", "最后 25% 按 9 EMA 收盘破位或前两根 K 高低点退出"),
        ),
        "avoid_steps": (
            ("最低锁定", "+1R 后至少止盈 50%"),
            ("保护动作", "+1R 后剩余止损移到入场价"),
            ("回吐上限", "从峰值回撤 0.5R 退出剩余仓位"),
        ),
        "factor_names": ("exit_efficiency", "pnl_result"),
        "review_reason_codes": ("profit_reversed", "exit_signal_ignored", "exit_plan_unclear"),
        "source_ids": ("market_intraday_momentum", "sec_day_trading_risk"),
    },
    {
        "catalog_order": 6,
        "family": "执行纪律",
        "execute_rule_id": "execute_position_and_plan_discipline",
        "avoid_rule_id": "avoid_execution_discipline_errors",
        "execute_title": "先确认仓位、方向、标的和计划再下单",
        "avoid_title": "规避仓位、重复下单和计划执行错误",
        "execute_condition": "每笔计划风险不超过复盘本金的 0.5%，同一标的同一方向同时只保留 1 个有效订单；当日累计 -2R 或连续亏损 3 笔后停止交易。",
        "avoid_condition": "仓位超过计划 10%、出现重复订单或方向/标的错误时立即取消；达到当日 -2R 或连续亏损 3 笔后不得再开新仓。",
        "execute_steps": (
            ("仓位风险", "每笔 ≤ 复盘本金的 0.5%"),
            ("订单唯一性", "同标的、同方向同时仅 1 个有效订单"),
            ("当日停手", "累计 -2R 或连续亏损 3 笔"),
        ),
        "avoid_steps": (
            ("仓位偏差", "实际风险 > 计划风险 10% 即取消"),
            ("误单处理", "重复、错方向或错标的立即取消"),
            ("禁止开仓", "当日 -2R 或连续亏损 3 笔后"),
        ),
        "factor_names": ("pnl_result", "mfe_mae"),
        "review_reason_codes": (
            "wrong_side_or_symbol",
            "oversized_position",
            "duplicate_order",
            "plan_not_followed",
        ),
        "source_ids": ("sec_day_trading_risk",),
    },
)


class TradeSummaryNarrativeRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=360)


class TradeSummaryNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1, max_length=80)
    overview: str = Field(min_length=1, max_length=600)
    execution_rules: list[TradeSummaryNarrativeRule]
    avoidance_rules: list[TradeSummaryNarrativeRule]


class TradeSummaryGenerationError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


ChatCompletionClient = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


def trade_summary_llm_configured(env: Mapping[str, str] | None = None) -> bool:
    try:
        _llm_config(env)
    except ValueError:
        return False
    return True


def get_trade_summary(
    conn: sqlite3.Connection,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    groups = _closed_trade_groups(conn, start_date=start_date, end_date=end_date)
    summary = _deterministic_summary(groups, start_date=start_date, end_date=end_date)
    summary["generation"] = _generation_projection(
        conn,
        summary,
        start_date=start_date,
        end_date=end_date,
        env=env,
    )
    return summary


def generate_trade_summary(
    conn: sqlite3.Connection,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    env: Mapping[str, str] | None = None,
    chat_client: ChatCompletionClient | None = None,
) -> dict[str, Any]:
    groups = _closed_trade_groups(conn, start_date=start_date, end_date=end_date)
    summary = _deterministic_summary(groups, start_date=start_date, end_date=end_date)
    if summary["evidence_status"] != "eligible":
        raise ValueError("trade_summary_personalization_insufficient")

    config = _llm_config(env)
    model_config_hash = _llm_model_config_hash(config)
    idempotency_key = _stable_hash(
        {
            "summary_key": summary["summary_key"],
            "prompt_version": TRADE_SUMMARY_PROMPT_VERSION,
            "provider": TRADE_SUMMARY_PROVIDER,
            "model": config["model"],
            "model_config_hash": model_config_hash,
        }
    )
    existing = row_to_dict(
        conn.execute(
            "SELECT * FROM trade_summary_generations WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
    )
    if existing and existing["generation_status"] == "completed":
        return get_trade_summary(conn, start_date=start_date, end_date=end_date, env=env)
    if existing and existing["generation_status"] == "pending":
        return get_trade_summary(conn, start_date=start_date, end_date=end_date, env=env)

    evidence_snapshot = _sanitized_evidence_snapshot(summary)
    deterministic_rules = {
        "execution_rules": summary["execution_rules"],
        "avoidance_rules": summary["avoidance_rules"],
    }
    parser_versions = sorted({version for group in groups for version in group.get("parser_versions", [])})
    field_mapper_versions = sorted(
        {version for group in groups for version in group.get("field_mapper_versions", [])}
    )
    now = _now()
    artifact_id = existing["id"] if existing else new_id("trade_summary_generation")
    retry_count = int(existing["retry_count"]) + 1 if existing else 0

    with conn:
        if existing:
            conn.execute(
                """
                UPDATE trade_summary_generations
                SET generation_status = 'pending', evidence_status = ?, evidence_snapshot_json = ?,
                    deterministic_rules_json = ?, ai_narrative_json = NULL, response_hash = NULL,
                    failure_reason = NULL, retry_count = ?, parser_versions_json = ?,
                    field_mapper_versions_json = ?, updated_at = ?, completed_at = NULL
                WHERE id = ?
                """,
                (
                    summary["evidence_status"],
                    _canonical_json(evidence_snapshot),
                    _canonical_json(deterministic_rules),
                    retry_count,
                    _canonical_json(parser_versions),
                    _canonical_json(field_mapper_versions),
                    now,
                    artifact_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO trade_summary_generations (
                    id, summary_key, idempotency_key, start_date, end_date,
                    evidence_status, generation_status, rule_catalog_version, prompt_version,
                    provider, model, model_config_hash, evidence_snapshot_json,
                    deterministic_rules_json, retry_count, parser_versions_json,
                    field_mapper_versions_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    summary["summary_key"],
                    idempotency_key,
                    start_date,
                    end_date,
                    summary["evidence_status"],
                    TRADE_SUMMARY_RULE_CATALOG_VERSION,
                    TRADE_SUMMARY_PROMPT_VERSION,
                    TRADE_SUMMARY_PROVIDER,
                    config["model"],
                    model_config_hash,
                    _canonical_json(evidence_snapshot),
                    _canonical_json(deterministic_rules),
                    retry_count,
                    _canonical_json(parser_versions),
                    _canonical_json(field_mapper_versions),
                    now,
                    now,
                ),
            )

    try:
        request_payload = _chat_completion_payload(summary, config["model"])
        response = (chat_client or _default_chat_completion_client)(
            f"{config['base_url'].rstrip('/')}/chat/completions",
            _chat_headers(config.get("api_key")),
            request_payload,
            60.0,
        )
        narrative = _validate_chat_completion_response(response, summary)
        response_hash = _stable_hash(response)
    except TradeSummaryGenerationError as exc:
        _fail_generation(conn, artifact_id, exc.code)
        return get_trade_summary(conn, start_date=start_date, end_date=end_date, env=env)
    except Exception:
        _fail_generation(conn, artifact_id, "trade_summary_llm_unavailable")
        return get_trade_summary(conn, start_date=start_date, end_date=end_date, env=env)

    completed_at = _now()
    with conn:
        conn.execute(
            """
            UPDATE trade_summary_generations
            SET generation_status = 'completed', ai_narrative_json = ?, response_hash = ?,
                failure_reason = NULL, updated_at = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                _canonical_json(narrative),
                response_hash,
                completed_at,
                completed_at,
                artifact_id,
            ),
        )
    return get_trade_summary(conn, start_date=start_date, end_date=end_date, env=env)


def record_session_trade_summary(
    conn: sqlite3.Connection,
    narrative: Mapping[str, Any],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    session_model: str = "codex_current_session",
) -> dict[str, Any]:
    """Persist a trusted, already-generated session narrative against recomputed evidence."""
    groups = _closed_trade_groups(conn, start_date=start_date, end_date=end_date)
    summary = _deterministic_summary(groups, start_date=start_date, end_date=end_date)
    if summary["evidence_status"] != "eligible":
        raise ValueError("trade_summary_personalization_insufficient")
    narrative_payload = _validate_narrative_payload(narrative, summary)
    model_config_hash = _stable_hash(
        {
            "provider": TRADE_SUMMARY_SESSION_PROVIDER,
            "model": session_model,
            "prompt_version": TRADE_SUMMARY_PROMPT_VERSION,
        }
    )
    idempotency_key = _stable_hash(
        {
            "summary_key": summary["summary_key"],
            "prompt_version": TRADE_SUMMARY_PROMPT_VERSION,
            "provider": TRADE_SUMMARY_SESSION_PROVIDER,
            "model": session_model,
            "model_config_hash": model_config_hash,
        }
    )
    existing = row_to_dict(
        conn.execute(
            "SELECT * FROM trade_summary_generations WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
    )
    evidence_snapshot = _sanitized_evidence_snapshot(summary)
    deterministic_rules = {
        "execution_rules": summary["execution_rules"],
        "avoidance_rules": summary["avoidance_rules"],
    }
    parser_versions = sorted({version for group in groups for version in group.get("parser_versions", [])})
    field_mapper_versions = sorted(
        {version for group in groups for version in group.get("field_mapper_versions", [])}
    )
    artifact_id = existing["id"] if existing else new_id("trade_summary_generation")
    now = _now()
    response_hash = _stable_hash(narrative_payload)
    with conn:
        if existing:
            conn.execute(
                """
                UPDATE trade_summary_generations
                SET generation_status = 'completed', evidence_status = ?, evidence_snapshot_json = ?,
                    deterministic_rules_json = ?, ai_narrative_json = ?, response_hash = ?,
                    failure_reason = NULL, parser_versions_json = ?, field_mapper_versions_json = ?,
                    updated_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    summary["evidence_status"],
                    _canonical_json(evidence_snapshot),
                    _canonical_json(deterministic_rules),
                    _canonical_json(narrative_payload),
                    response_hash,
                    _canonical_json(parser_versions),
                    _canonical_json(field_mapper_versions),
                    now,
                    now,
                    artifact_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO trade_summary_generations (
                    id, summary_key, idempotency_key, start_date, end_date,
                    evidence_status, generation_status, rule_catalog_version, prompt_version,
                    provider, model, model_config_hash, evidence_snapshot_json,
                    deterministic_rules_json, ai_narrative_json, response_hash, retry_count,
                    parser_versions_json, field_mapper_versions_json, created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    summary["summary_key"],
                    idempotency_key,
                    start_date,
                    end_date,
                    summary["evidence_status"],
                    TRADE_SUMMARY_RULE_CATALOG_VERSION,
                    TRADE_SUMMARY_PROMPT_VERSION,
                    TRADE_SUMMARY_SESSION_PROVIDER,
                    session_model,
                    model_config_hash,
                    _canonical_json(evidence_snapshot),
                    _canonical_json(deterministic_rules),
                    _canonical_json(narrative_payload),
                    response_hash,
                    _canonical_json(parser_versions),
                    _canonical_json(field_mapper_versions),
                    now,
                    now,
                    now,
                ),
            )
    return get_trade_summary(conn, start_date=start_date, end_date=end_date, env={})


def _closed_trade_groups(
    conn: sqlite3.Connection,
    *,
    start_date: str | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    groups = _trade_summary_groups(conn, start_date=start_date, end_date=end_date)
    return [
        group
        for group in groups
        if group["status"] == "closed"
        and group["pnl"] is not None
        and (start_date is None or _trade_group_date(group) >= start_date)
        and (end_date is None or _trade_group_date(group) <= end_date)
    ]


def _trade_summary_groups(
    conn: sqlite3.Connection,
    *,
    start_date: str | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    groups = [
        group
        for group in _light_trade_groups(conn)
        if group["status"] == "closed"
        and group["pnl"] is not None
        and (start_date is None or _trade_group_date(group) >= start_date)
        and (end_date is None or _trade_group_date(group) <= end_date)
    ]
    if not groups:
        return []

    archive_keys = {(group["symbol"], str(group["opened_at"])[:10]) for group in groups}
    archives: dict[tuple[str, str], dict[str, Any]] = {}
    for row in conn.execute(
        """
        SELECT * FROM market_minute_archives
        WHERE provider = 'yahoo'
        ORDER BY symbol, trade_date, created_at DESC, id DESC
        """
    ).fetchall():
        archive = row_to_dict(row)
        key = (archive["symbol"], archive["trade_date"])
        if key in archive_keys and key not in archives:
            archives[key] = archive

    reviews = {
        row["trade_group_id"]: _public_trade_review(row_to_dict(row))
        for row in conn.execute("SELECT * FROM trade_reviews").fetchall()
    }
    bars_cache: dict[str, tuple[list[dict[str, Any]], list[tuple[int | None, dict[str, Any]]]]] = {}
    result: list[dict[str, Any]] = []
    for group in groups:
        archive = archives.get((group["symbol"], str(group["opened_at"])[:10]))
        evaluation = {"evaluation_status": "insufficient_market_data", "factors": []}
        position_drawdown = {"source_archive_id": None, "bars_hash": None}
        if archive and archive["data_status"] not in {"provider_failed", "missing", "timezone_conflict"}:
            cached_bars = bars_cache.get(archive["id"])
            if cached_bars is None:
                bars = json.loads(archive["bars_json"])
                cached_bars = (
                    bars,
                    [(_clock_minute(str(bar.get("timestamp", ""))), bar) for bar in bars],
                )
                bars_cache[archive["id"]] = cached_bars
            bars, minute_bars = cached_bars
            if bars:
                opened_minute = _clock_minute(str(group["opened_at"]))
                closed_minute = _clock_minute(str(group["closed_at"]))
                if opened_minute is None or closed_minute is None:
                    scoped_bars = bars
                else:
                    scoped_bars = [
                        bar
                        for minute, bar in minute_bars
                        if minute is not None and opened_minute <= minute <= closed_minute
                    ]
                factors = _trade_evaluation_factors(group, scoped_bars or bars, archive)
                evaluation = {"evaluation_status": "available", "factors": factors}
                if scoped_bars and _trade_group_path_drawdown(group, scoped_bars) is not None:
                    position_drawdown = {
                        "source_archive_id": archive["id"],
                        "bars_hash": archive["bars_hash"],
                    }
        result.append(
            {
                **group,
                "evaluation": evaluation,
                "position_drawdown": position_drawdown,
                "review": reviews.get(group["trade_group_id"]),
            }
        )
    return result


def _deterministic_summary(
    groups: list[dict[str, Any]],
    *,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    wins = [group for group in groups if float(group["pnl"]) > 0]
    losses = [group for group in groups if float(group["pnl"]) < 0]
    flats = [group for group in groups if abs(float(group["pnl"])) < 1e-9]
    evaluated = [group for group in groups if group["evaluation"]["evaluation_status"] == "available"]
    reviewed_losses = [group for group in losses if group.get("review") is not None]
    gross_profit = sum(float(group["pnl"]) for group in wins)
    gross_loss = abs(sum(float(group["pnl"]) for group in losses))
    evidence_status = _evidence_status(len(groups), len(wins), len(losses))
    gaps = {
        "closed_trades_needed": max(0, TRADE_SUMMARY_MIN_CLOSED_TRADES - len(groups)),
        "wins_needed": max(0, TRADE_SUMMARY_MIN_WINS - len(wins)),
        "losses_needed": max(0, TRADE_SUMMARY_MIN_LOSSES - len(losses)),
    }
    execution_rules: list[dict[str, Any]] = []
    avoidance_rules: list[dict[str, Any]] = []
    for catalog_rule in TRADE_SUMMARY_RULE_CATALOG:
        win_supports = [group for group in wins if _rule_has_win_support(group, catalog_rule)]
        loss_hits = [group for group in losses if _rule_has_loss_hit(group, catalog_rule)]
        observed_wins = [group for group in wins if _rule_has_observable_win_evidence(group, catalog_rule)]
        observed_losses = [group for group in losses if _rule_has_observable_loss_evidence(group, catalog_rule)]
        winning_support_pnl = round(sum(float(group["pnl"]) for group in win_supports), 6)
        loss_impact = round(abs(sum(float(group["pnl"]) for group in loss_hits)), 6)
        quantification = {
            "winning_observed_count": len(observed_wins),
            "winning_support_count": len(win_supports),
            "winning_support_rate": _safe_ratio(len(win_supports), len(observed_wins)),
            "winning_support_pnl": winning_support_pnl,
            "average_winning_support_pnl": _safe_average(winning_support_pnl, len(win_supports)),
            "loss_observed_count": len(observed_losses),
            "loss_hit_count": len(loss_hits),
            "loss_hit_rate": _safe_ratio(len(loss_hits), len(observed_losses)),
            "loss_impact": loss_impact,
            "average_loss_impact": _safe_average(loss_impact, len(loss_hits)),
        }
        common = {
            "family": catalog_rule["family"],
            "source_ids": list(catalog_rule["source_ids"]),
            "catalog_order": catalog_rule["catalog_order"],
            "winning_support_count": len(win_supports),
            "loss_hit_count": len(loss_hits),
            "winning_support_pnl": winning_support_pnl,
            "loss_impact": loss_impact,
            "quantification": quantification,
        }
        if (
            evidence_status == "eligible"
            and len(win_supports) >= TRADE_SUMMARY_MIN_RULE_EVIDENCE
            and len(loss_hits) >= TRADE_SUMMARY_MIN_RULE_EVIDENCE
        ):
            execution_rules.append(
                {
                    **common,
                    "rule_id": catalog_rule["execute_rule_id"],
                    "title": catalog_rule["execute_title"],
                    "condition": catalog_rule["execute_condition"],
                    "action_steps": _action_steps(catalog_rule["execute_steps"]),
                    "evidence_count": len(win_supports) + len(loss_hits),
                    "impact_amount": round(
                        sum(float(group["pnl"]) for group in win_supports)
                        + abs(sum(float(group["pnl"]) for group in loss_hits)),
                        6,
                    ),
                }
            )
        if evidence_status == "eligible" and len(loss_hits) >= TRADE_SUMMARY_MIN_RULE_EVIDENCE:
            avoidance_rules.append(
                {
                    **common,
                    "rule_id": catalog_rule["avoid_rule_id"],
                    "title": catalog_rule["avoid_title"],
                    "condition": catalog_rule["avoid_condition"],
                    "action_steps": _action_steps(catalog_rule["avoid_steps"]),
                    "evidence_count": len(loss_hits),
                    "impact_amount": round(abs(sum(float(group["pnl"]) for group in loss_hits)), 6),
                }
            )
    execution_rules.sort(
        key=lambda rule: (-int(rule["evidence_count"]), -float(rule["impact_amount"]), int(rule["catalog_order"]))
    )
    avoidance_rules.sort(
        key=lambda rule: (-float(rule["loss_impact"]), -int(rule["loss_hit_count"]), int(rule["catalog_order"]))
    )

    evidence_signature = [
        {
            "trade_group_id": group["trade_group_id"],
            "pnl": group["pnl"],
            "evaluation_status": group["evaluation"]["evaluation_status"],
            "factors": [
                {
                    "name": factor["name"],
                    "score": factor["score"],
                    "max_score": factor["max_score"],
                }
                for factor in group["evaluation"].get("factors", [])
            ],
            "archive_id": group["position_drawdown"].get("source_archive_id"),
            "bars_hash": group["position_drawdown"].get("bars_hash"),
            "review_reason_code": group.get("review", {}).get("reason_code") if group.get("review") else None,
            "review_updated_at": group.get("review", {}).get("updated_at") if group.get("review") else None,
        }
        for group in sorted(groups, key=lambda group: group["trade_group_id"])
    ]
    summary_key = _stable_hash(
        {
            "rule_catalog_version": TRADE_SUMMARY_RULE_CATALOG_VERSION,
            "evaluation_model_version": TRADE_EVALUATION_MODEL_VERSION,
            "start_date": start_date,
            "end_date": end_date,
            "groups": evidence_signature,
        }
    )
    return {
        "contract_version": TRADE_SUMMARY_CONTRACT_VERSION,
        "rule_catalog_version": TRADE_SUMMARY_RULE_CATALOG_VERSION,
        "evaluation_model_version": TRADE_EVALUATION_MODEL_VERSION,
        "prompt_version": TRADE_SUMMARY_PROMPT_VERSION,
        "scope": {"start_date": start_date, "end_date": end_date},
        "evidence_status": evidence_status,
        "thresholds": {
            "minimum_closed_trades": TRADE_SUMMARY_MIN_CLOSED_TRADES,
            "minimum_wins": TRADE_SUMMARY_MIN_WINS,
            "minimum_losses": TRADE_SUMMARY_MIN_LOSSES,
            "minimum_rule_evidence": TRADE_SUMMARY_MIN_RULE_EVIDENCE,
            "winning_support_ratio": TRADE_SUMMARY_WIN_SUPPORT_THRESHOLD,
            "loss_weakness_ratio": TRADE_SUMMARY_LOSS_WEAKNESS_THRESHOLD,
        },
        "gaps": gaps,
        "progress": {
            "closed_trades": min(1.0, len(groups) / TRADE_SUMMARY_MIN_CLOSED_TRADES),
            "wins": min(1.0, len(wins) / TRADE_SUMMARY_MIN_WINS),
            "losses": min(1.0, len(losses) / TRADE_SUMMARY_MIN_LOSSES),
        },
        "metrics": {
            "closed_trade_count": len(groups),
            "win_count": len(wins),
            "loss_count": len(losses),
            "flat_count": len(flats),
            "pnl": round(sum(float(group["pnl"]) for group in groups), 6),
            "profit_factor": None if gross_loss == 0 else round(gross_profit / gross_loss, 6),
            "evaluated_trade_count": len(evaluated),
            "evaluation_coverage_ratio": 0.0 if not groups else round(len(evaluated) / len(groups), 6),
            "reviewed_loss_count": len(reviewed_losses),
            "loss_journal_coverage_ratio": 0.0 if not losses else round(len(reviewed_losses) / len(losses), 6),
        },
        "classic_baselines": _classic_baselines(),
        "execution_rules": execution_rules,
        "avoidance_rules": avoidance_rules,
        "summary_key": summary_key,
        "sources": TRADE_SUMMARY_SOURCES,
        "disclaimer": "本页用于复盘与执行纪律改进，不构成投资建议、收益承诺或自动交易指令。",
    }


def _classic_baselines() -> list[dict[str, Any]]:
    return [
        {
            "family": rule["family"],
            "rule_id": rule["execute_rule_id"],
            "title": rule["execute_title"],
            "condition": rule["execute_condition"],
            "action_steps": _action_steps(rule["execute_steps"]),
            "source_ids": list(rule["source_ids"]),
            "catalog_order": rule["catalog_order"],
        }
        for rule in TRADE_SUMMARY_RULE_CATALOG
    ]


def _rule_has_win_support(group: dict[str, Any], rule: dict[str, Any]) -> bool:
    factors = _normalized_factors(group)
    return any(
        factors.get(name) is not None and float(factors[name]) >= TRADE_SUMMARY_WIN_SUPPORT_THRESHOLD
        for name in rule["factor_names"]
    )


def _rule_has_observable_win_evidence(group: dict[str, Any], rule: dict[str, Any]) -> bool:
    factors = _normalized_factors(group)
    return any(factors.get(name) is not None for name in rule["factor_names"])


def _rule_has_loss_hit(group: dict[str, Any], rule: dict[str, Any]) -> bool:
    factors = _normalized_factors(group)
    factor_hit = any(
        factors.get(name) is not None and float(factors[name]) < TRADE_SUMMARY_LOSS_WEAKNESS_THRESHOLD
        for name in rule["factor_names"]
    )
    review = group.get("review")
    review_hit = bool(review and review.get("reason_code") in rule["review_reason_codes"])
    return factor_hit or review_hit


def _rule_has_observable_loss_evidence(group: dict[str, Any], rule: dict[str, Any]) -> bool:
    factors = _normalized_factors(group)
    factor_observed = any(factors.get(name) is not None for name in rule["factor_names"])
    return factor_observed or group.get("review") is not None


def _normalized_factors(group: dict[str, Any]) -> dict[str, float]:
    if group["evaluation"]["evaluation_status"] != "available":
        return {}
    result: dict[str, float] = {}
    for factor in group["evaluation"].get("factors", []):
        maximum = float(factor.get("max_score") or 0)
        if maximum > 0:
            result[str(factor["name"])] = float(factor.get("score") or 0) / maximum
    return result


def _generation_projection(
    conn: sqlite3.Connection,
    summary: dict[str, Any],
    *,
    start_date: str | None,
    end_date: str | None,
    env: Mapping[str, str] | None,
) -> dict[str, Any]:
    try:
        config = _llm_config(env)
    except ValueError:
        config = None
    current_model_config_hash = _llm_model_config_hash(config) if config else None
    session_exact = row_to_dict(
        conn.execute(
            """
            SELECT * FROM trade_summary_generations
            WHERE summary_key = ? AND prompt_version = ? AND provider = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (
                summary["summary_key"],
                TRADE_SUMMARY_PROMPT_VERSION,
                TRADE_SUMMARY_SESSION_PROVIDER,
            ),
        ).fetchone()
    )
    exact_current = None
    if config:
        exact_current = row_to_dict(
            conn.execute(
                """
                SELECT * FROM trade_summary_generations
                WHERE summary_key = ? AND prompt_version = ? AND provider = ?
                  AND model = ? AND model_config_hash = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (
                    summary["summary_key"],
                    TRADE_SUMMARY_PROMPT_VERSION,
                    TRADE_SUMMARY_PROVIDER,
                    config["model"],
                    current_model_config_hash,
                ),
            ).fetchone()
        )
    exact_latest = row_to_dict(
        conn.execute(
            """
            SELECT * FROM trade_summary_generations
            WHERE summary_key = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (summary["summary_key"],),
        ).fetchone()
    )
    scope_latest = row_to_dict(
        conn.execute(
            """
            SELECT * FROM trade_summary_generations
            WHERE COALESCE(start_date, '') = COALESCE(?, '')
              AND COALESCE(end_date, '') = COALESCE(?, '')
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (start_date, end_date),
        ).fetchone()
    )
    artifact = session_exact or exact_current or exact_latest or scope_latest
    if session_exact:
        status = session_exact["generation_status"]
    elif exact_current:
        status = exact_current["generation_status"]
    elif exact_latest and not config and exact_latest["prompt_version"] == TRADE_SUMMARY_PROMPT_VERSION:
        status = exact_latest["generation_status"]
    elif exact_latest or scope_latest:
        status = "stale"
    elif not config:
        status = "unconfigured"
    else:
        status = "not_requested"
    return {
        "status": status,
        "llm_configured": config is not None,
        "current_model": config["model"] if config else None,
        "provider": artifact["provider"] if artifact else None,
        "artifact_id": artifact["id"] if artifact else None,
        "artifact_summary_key": artifact["summary_key"] if artifact else None,
        "model": artifact["model"] if artifact else None,
        "retry_count": int(artifact["retry_count"]) if artifact else 0,
        "failure_reason": artifact["failure_reason"] if artifact and status == "failed" else None,
        "created_at": artifact["created_at"] if artifact else None,
        "updated_at": artifact["updated_at"] if artifact else None,
        "completed_at": artifact["completed_at"] if artifact else None,
        "narrative": (
            _json_or_none(artifact.get("ai_narrative_json"))
            if artifact and status == "completed"
            else None
        ),
    }


def _sanitized_evidence_snapshot(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": summary["contract_version"],
        "rule_catalog_version": summary["rule_catalog_version"],
        "evaluation_model_version": summary["evaluation_model_version"],
        "scope": summary["scope"],
        "evidence_status": summary["evidence_status"],
        "thresholds": summary["thresholds"],
        "gaps": summary["gaps"],
        "metrics": summary["metrics"],
        "execution_rules": [_prompt_rule(rule) for rule in summary["execution_rules"]],
        "avoidance_rules": [_prompt_rule(rule) for rule in summary["avoidance_rules"]],
    }


def _chat_completion_payload(summary: dict[str, Any], model: str) -> dict[str, Any]:
    evidence = _sanitized_evidence_snapshot(summary)
    schema_hint = {
        "headline": "不含数字的简短标题",
        "overview": "不含数字的证据边界摘要",
        "execution_rules": [{"rule_id": "必须原样返回输入规则 ID", "text": "只改写既有规则"}],
        "avoidance_rules": [{"rule_id": "必须原样返回输入规则 ID", "text": "只改写既有规则"}],
    }
    return {
        "model": model,
        "temperature": 0,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是交易复盘文案编辑器。只能改写输入中的确定性规则，不得新增规则、数字、"
                    "交易结论或盈利承诺。输出严格 JSON，不使用 Markdown。"
                ),
            },
            {
                "role": "user",
                "content": _canonical_json({"evidence": evidence, "required_output": schema_hint}),
            },
        ],
    }


def _validate_chat_completion_response(response: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TradeSummaryGenerationError("trade_summary_llm_invalid_response") from exc
    if not isinstance(content, str):
        raise TradeSummaryGenerationError("trade_summary_llm_invalid_response")
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        raw = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise TradeSummaryGenerationError("trade_summary_llm_invalid_json") from exc

    return _validate_narrative_payload(raw, summary)


def _validate_narrative_payload(raw: Mapping[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    try:
        narrative = TradeSummaryNarrative.model_validate(raw)
    except ValidationError as exc:
        raise TradeSummaryGenerationError("trade_summary_llm_invalid_json") from exc

    expected_execution_ids = [rule["rule_id"] for rule in summary["execution_rules"]]
    expected_avoidance_ids = [rule["rule_id"] for rule in summary["avoidance_rules"]]
    actual_execution_ids = [rule.rule_id for rule in narrative.execution_rules]
    actual_avoidance_ids = [rule.rule_id for rule in narrative.avoidance_rules]
    if actual_execution_ids != expected_execution_ids or actual_avoidance_ids != expected_avoidance_ids:
        raise TradeSummaryGenerationError("trade_summary_llm_rule_id_mismatch")
    narrative_payload = narrative.model_dump()
    text_values = [narrative.headline, narrative.overview]
    text_values.extend(rule.text for rule in narrative.execution_rules)
    text_values.extend(rule.text for rule in narrative.avoidance_rules)
    if any(re.search(r"[0-9０-９$¥￥%％]", value) for value in text_values):
        raise TradeSummaryGenerationError("trade_summary_llm_new_number_rejected")
    return narrative_payload


def _default_chat_completion_client(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=_canonical_json(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            if status < 200 or status >= 300:
                raise TradeSummaryGenerationError("trade_summary_llm_http_error")
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise TradeSummaryGenerationError("trade_summary_llm_http_error") from exc
    except TimeoutError as exc:
        raise TradeSummaryGenerationError("trade_summary_llm_timeout") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise TradeSummaryGenerationError("trade_summary_llm_unavailable") from exc
    except json.JSONDecodeError as exc:
        raise TradeSummaryGenerationError("trade_summary_llm_invalid_response") from exc


def _llm_config(env: Mapping[str, str] | None) -> dict[str, str]:
    source = os.environ if env is None else env
    base_url = str(source.get("GRIT_REVIEW_LLM_BASE_URL", "")).strip()
    model = str(source.get("GRIT_REVIEW_LLM_MODEL", "")).strip()
    api_key = str(source.get("GRIT_REVIEW_LLM_API_KEY", "")).strip()
    if not base_url or not model:
        raise ValueError("trade_summary_llm_unconfigured")
    parsed = urlsplit(base_url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password:
        raise ValueError("trade_summary_llm_invalid_base_url")
    if parsed.query or parsed.fragment or not parsed.path.rstrip("/").endswith("/v1"):
        raise ValueError("trade_summary_llm_invalid_base_url")
    try:
        is_loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        is_loopback = hostname == "localhost"
    if not is_loopback:
        raise ValueError("trade_summary_llm_non_loopback_rejected")
    return {"base_url": base_url.rstrip("/"), "model": model, "api_key": api_key}


def _chat_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _prompt_rule(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": rule["rule_id"],
        "family": rule["family"],
        "title": rule["title"],
        "condition": rule["condition"],
        "evidence_count": rule["evidence_count"],
        "winning_support_count": rule["winning_support_count"],
        "loss_hit_count": rule["loss_hit_count"],
        "impact_amount": rule["impact_amount"],
        "quantification": rule["quantification"],
        "action_steps": rule["action_steps"],
    }


def _action_steps(steps: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [{"label": label, "value": value} for label, value in steps]


def _llm_model_config_hash(config: Mapping[str, str]) -> str:
    return _stable_hash(
        {
            "base_url": config["base_url"],
            "model": config["model"],
            "temperature": 0,
            "stream": False,
            "timeout_seconds": 60,
        }
    )


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _safe_average(total: float, count: int) -> float | None:
    if count <= 0:
        return None
    return round(total / count, 6)


def _evidence_status(closed_count: int, win_count: int, loss_count: int) -> str:
    if closed_count == 0:
        return "no_trades"
    if (
        closed_count < TRADE_SUMMARY_MIN_CLOSED_TRADES
        or win_count < TRADE_SUMMARY_MIN_WINS
        or loss_count < TRADE_SUMMARY_MIN_LOSSES
    ):
        return "insufficient_sample"
    return "eligible"


def _trade_group_date(group: dict[str, Any]) -> str:
    return str(group["closed_at"] or group["opened_at"])[:10]


def _fail_generation(conn: sqlite3.Connection, artifact_id: str, failure_reason: str) -> None:
    now = _now()
    with conn:
        conn.execute(
            """
            UPDATE trade_summary_generations
            SET generation_status = 'failed', failure_reason = ?, updated_at = ?, completed_at = NULL
            WHERE id = ?
            """,
            (failure_reason, now, artifact_id),
        )


def _json_or_none(value: Any) -> Any:
    if value in (None, ""):
        return None
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
