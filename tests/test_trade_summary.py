from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import grit_day_trading.trade_summary as trade_summary_module
from grit_day_trading.api import create_app
from grit_day_trading.storage import connect, initialize_database
from grit_day_trading.trade_summary import generate_trade_summary, get_trade_summary, record_session_trade_summary


FACTOR_MAXIMUMS = {
    "vwap_execution": 20,
    "momentum_alignment": 20,
    "volume_confirmation": 15,
    "mfe_mae": 20,
    "exit_efficiency": 15,
    "pnl_result": 10,
}


def _group(index: int, pnl: float, *, evaluation_available: bool = True, reviewed: bool = False):
    ratio = 0.9 if pnl > 0 else (0.2 if pnl < 0 else 0.5)
    factors = [
        {
            "name": name,
            "label": name,
            "score": maximum * ratio,
            "max_score": maximum,
            "detail": "deterministic",
        }
        for name, maximum in FACTOR_MAXIMUMS.items()
    ]
    review = None
    if reviewed and pnl < 0:
        review = {
            "reason_category": "opening_signal",
            "reason_code": "chased_breakout",
            "updated_at": f"2026-07-{index + 1:02d}T12:00:00+00:00",
            "note": "敏感复盘自由文本",
        }
    day = 1 + (index % 20)
    return {
        "id": f"tg_{index:03d}",
        "trade_group_id": f"tg_{index:03d}",
        "account_canonical": "SECRET_ACCOUNT",
        "status": "closed",
        "opened_at": f"2026-07-{day:02d}T09:30:00",
        "closed_at": f"2026-07-{day:02d}T10:00:00",
        "pnl": pnl,
        "parser_versions": ["stp_parser_v3"],
        "field_mapper_versions": ["stp_field_mapper_v3"],
        "fills": [{"fill_id": f"secret_fill_{index}"}],
        "evaluation": {
            "model_version": "trade_eval_intraday_v1",
            "evaluation_status": "available" if evaluation_available else "insufficient_market_data",
            "factors": factors if evaluation_available else [],
        },
        "position_drawdown": {
            "source_archive_id": f"archive_{day:02d}" if evaluation_available else None,
            "bars_hash": f"bars_hash_{day:02d}" if evaluation_available else None,
        },
        "review": review,
    }


def _eligible_groups():
    return [
        *[_group(index, 120 + index) for index in range(10)],
        *[_group(index, -(70 + index), reviewed=index < 15) for index in range(10, 18)],
        _group(18, 0),
        _group(19, 0),
    ]


def _configured_env(base_url: str = "http://127.0.0.1:11434/v1"):
    return {
        "GRIT_REVIEW_LLM_BASE_URL": base_url,
        "GRIT_REVIEW_LLM_MODEL": "local-review-model",
        "GRIT_REVIEW_LLM_API_KEY": "secret-token",
    }


def _valid_response(summary):
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "headline": "执行证据已形成稳定方向",
                            "overview": "建议保持已验证的执行条件，并优先修正重复出现的亏损弱项。",
                            "execution_rules": [
                                {"rule_id": rule["rule_id"], "text": "保持该条件确认后再执行。"}
                                for rule in summary["execution_rules"]
                            ],
                            "avoidance_rules": [
                                {"rule_id": rule["rule_id"], "text": "出现该风险条件时停止执行。"}
                                for rule in summary["avoidance_rules"]
                            ],
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }


def test_trade_summary_group_loader_batches_shared_market_and_journal_evidence(tmp_path, monkeypatch):
    conn = connect(tmp_path / "batched-summary.db")
    initialize_database(conn)
    bars = [
        {"timestamp": "2026-07-01T09:30:00", "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 100},
        {"timestamp": "2026-07-01T09:31:00", "open": 10.1, "high": 10.4, "low": 10.0, "close": 10.3, "volume": 120},
        {"timestamp": "2026-07-01T09:32:00", "open": 10.3, "high": 10.5, "low": 10.2, "close": 10.4, "volume": 140},
        {"timestamp": "2026-07-01T09:33:00", "open": 10.4, "high": 10.6, "low": 10.3, "close": 10.5, "volume": 160},
    ]
    bars_json = json.dumps(bars)
    with conn:
        conn.execute(
            """
            INSERT INTO market_minute_archives (
                id, provider, symbol, trade_date, requested_start, requested_end, provider_timezone,
                bar_count, bars_hash, bars_json, volume_context, data_status, source_fill_count,
                archive_version, idempotency_key
            ) VALUES (
                'archive_shared', 'yahoo', 'MU', '2026-07-01', '2026-07-01T04:00:00',
                '2026-07-01T20:00:00', 'America/New_York', 4, 'bars_shared', ?,
                '{"avg_bar_volume": 130}', 'available', 4, 'market_minute_archive_v1', 'shared-archive'
            )
            """,
            (bars_json,),
        )

    def group(index: int, opened: str, closed: str, entry: float, exit_price: float):
        return {
            "id": f"tg_batch_{index}",
            "trade_group_id": f"tg_batch_{index}",
            "account_canonical": "ACCOUNT",
            "symbol": "MU",
            "direction": "LONG",
            "status": "closed",
            "opened_at": opened,
            "closed_at": closed,
            "avg_entry_price": entry,
            "avg_exit_price": exit_price,
            "pnl": exit_price - entry,
            "parser_versions": ["stp_parser_v3"],
            "field_mapper_versions": ["stp_field_mapper_v3"],
            "fills": [
                {"fill_id": f"entry_{index}", "side": "BUY", "filled_at": opened, "quantity": 1, "price": entry},
                {"fill_id": f"exit_{index}", "side": "SELL", "filled_at": closed, "quantity": 1, "price": exit_price},
            ],
        }

    groups = [
        group(1, "2026-07-01T09:30:00", "2026-07-01T09:31:00", 10.0, 10.3),
        group(2, "2026-07-01T09:32:00", "2026-07-01T09:33:00", 10.3, 10.5),
    ]
    monkeypatch.setattr(trade_summary_module, "_light_trade_groups", lambda *_args, **_kwargs: groups)
    original_loads = json.loads
    bars_decode_count = 0

    def counted_loads(value, *args, **kwargs):
        nonlocal bars_decode_count
        if value == bars_json:
            bars_decode_count += 1
        return original_loads(value, *args, **kwargs)

    monkeypatch.setattr(trade_summary_module.json, "loads", counted_loads)
    statements = []
    conn.set_trace_callback(statements.append)

    loaded = trade_summary_module._trade_summary_groups(conn, start_date=None, end_date=None)

    assert len(loaded) == 2
    assert all(item["evaluation"]["evaluation_status"] == "available" for item in loaded)
    assert bars_decode_count == 1
    assert sum("FROM market_minute_archives" in statement for statement in statements) == 1
    assert sum("FROM trade_reviews" in statement for statement in statements) == 1
    conn.close()


def test_deterministic_summary_applies_thresholds_classification_normalization_and_stable_sort(tmp_path, monkeypatch):
    conn = connect(tmp_path / "summary.db")
    initialize_database(conn)
    groups = _eligible_groups()
    monkeypatch.setattr(trade_summary_module, "_trade_summary_groups", lambda *_args, **_kwargs: groups)

    summary = get_trade_summary(conn, env=_configured_env())

    assert summary["evidence_status"] == "eligible"
    assert summary["metrics"] == {
        "closed_trade_count": 20,
        "win_count": 10,
        "loss_count": 8,
        "flat_count": 2,
        "pnl": pytest.approx(577),
        "profit_factor": pytest.approx(1245 / 668),
        "evaluated_trade_count": 20,
        "evaluation_coverage_ratio": 1.0,
        "reviewed_loss_count": 5,
        "loss_journal_coverage_ratio": 0.625,
    }
    assert summary["gaps"] == {"closed_trades_needed": 0, "wins_needed": 0, "losses_needed": 0}
    assert len(summary["execution_rules"]) == 6
    assert len(summary["avoidance_rules"]) == 6
    first_rule_quantification = summary["execution_rules"][0]["quantification"]
    assert first_rule_quantification["winning_observed_count"] == 10
    assert first_rule_quantification["winning_support_count"] == 10
    assert first_rule_quantification["winning_support_rate"] == 1.0
    assert first_rule_quantification["loss_observed_count"] == 8
    assert first_rule_quantification["loss_hit_count"] == 8
    assert first_rule_quantification["loss_hit_rate"] == 1.0
    assert first_rule_quantification["average_winning_support_pnl"] == pytest.approx(124.5)
    assert first_rule_quantification["average_loss_impact"] == pytest.approx(83.5)
    assert [rule["loss_impact"] for rule in summary["avoidance_rules"]] == sorted(
        [rule["loss_impact"] for rule in summary["avoidance_rules"]], reverse=True
    )
    assert summary["generation"]["status"] == "not_requested"
    assert summary["generation"]["current_model"] == "local-review-model"
    assert summary["rule_catalog_version"] == "intraday_review_rule_catalog_v2"
    profit_rule = next(rule for rule in summary["execution_rules"] if rule["family"] == "盈利保护")
    assert "+1R 时止盈 50%" in profit_rule["condition"]
    assert profit_rule["action_steps"] == [
        {"label": "第一目标", "value": "+1R 止盈 50%，止损移到入场价"},
        {"label": "第二目标", "value": "+2R 再止盈 25%"},
        {"label": "尾仓管理", "value": "最后 25% 按 9 EMA 收盘破位或前两根 K 高低点退出"},
    ]
    conn.close()


def test_date_scope_missing_market_evidence_and_missing_journal_are_not_false_negative_evidence(tmp_path, monkeypatch):
    conn = connect(tmp_path / "scope.db")
    initialize_database(conn)
    groups = [_group(0, 10, evaluation_available=False), _group(1, -10, evaluation_available=False)]
    monkeypatch.setattr(trade_summary_module, "_trade_summary_groups", lambda *_args, **_kwargs: groups)

    summary = get_trade_summary(conn, start_date="2026-07-01", end_date="2026-07-01")

    assert summary["metrics"]["closed_trade_count"] == 1
    assert summary["metrics"]["evaluation_coverage_ratio"] == 0
    assert summary["metrics"]["loss_journal_coverage_ratio"] == 0
    assert summary["execution_rules"] == []
    assert summary["avoidance_rules"] == []
    assert summary["evidence_status"] == "insufficient_sample"
    conn.close()


def test_summary_key_is_stable_and_changes_with_review_evidence(tmp_path, monkeypatch):
    conn = connect(tmp_path / "key.db")
    initialize_database(conn)
    groups = _eligible_groups()
    monkeypatch.setattr(trade_summary_module, "_trade_summary_groups", lambda *_args, **_kwargs: groups)
    first = get_trade_summary(conn, env=_configured_env())
    second = get_trade_summary(conn, env=_configured_env())
    assert first["summary_key"] == second["summary_key"]

    groups[10]["review"] = {
        "reason_category": "closing_signal",
        "reason_code": "profit_reversed",
        "updated_at": "2026-07-22T12:00:00+00:00",
        "note": "不会进入 hash 明文之外的 prompt",
    }
    changed = get_trade_summary(conn, env=_configured_env())
    assert changed["summary_key"] != first["summary_key"]
    conn.close()


def test_rule_quantification_excludes_missing_evidence_from_rate_denominators(tmp_path, monkeypatch):
    conn = connect(tmp_path / "quantification.db")
    initialize_database(conn)
    groups = _eligible_groups()
    groups[0]["evaluation"] = {
        "model_version": "trade_eval_intraday_v1",
        "evaluation_status": "insufficient_market_data",
        "factors": [],
    }
    groups[17]["evaluation"] = {
        "model_version": "trade_eval_intraday_v1",
        "evaluation_status": "insufficient_market_data",
        "factors": [],
    }
    monkeypatch.setattr(trade_summary_module, "_trade_summary_groups", lambda *_args, **_kwargs: groups)

    summary = get_trade_summary(conn, env=_configured_env())
    quantification = summary["execution_rules"][0]["quantification"]

    assert quantification["winning_observed_count"] == 9
    assert quantification["winning_support_count"] == 9
    assert quantification["winning_support_rate"] == 1.0
    assert quantification["loss_observed_count"] == 7
    assert quantification["loss_hit_count"] == 7
    assert quantification["loss_hit_rate"] == 1.0
    conn.close()


def test_generation_is_redacted_validated_persisted_and_reused(tmp_path, monkeypatch):
    conn = connect(tmp_path / "generation.db")
    initialize_database(conn)
    groups = _eligible_groups()
    monkeypatch.setattr(trade_summary_module, "_trade_summary_groups", lambda *_args, **_kwargs: groups)
    calls = []

    def client(url, headers, payload, timeout):
        calls.append((url, headers, payload, timeout))
        summary = get_trade_summary(conn, env=_configured_env())
        return _valid_response(summary)

    generated = generate_trade_summary(conn, env=_configured_env(), chat_client=client)
    reused = generate_trade_summary(conn, env=_configured_env(), chat_client=client)

    assert generated["generation"]["status"] == "completed"
    assert reused["generation"]["artifact_id"] == generated["generation"]["artifact_id"]
    assert len(calls) == 1
    url, headers, payload, timeout = calls[0]
    assert url == "http://127.0.0.1:11434/v1/chat/completions"
    assert headers["Authorization"] == "Bearer secret-token"
    assert payload["temperature"] == 0
    assert payload["stream"] is False
    assert timeout == 60
    external_payload = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("SECRET_ACCOUNT", "secret_fill", "account_canonical", "trade_group_id", "敏感复盘自由文本"):
        assert forbidden not in external_payload
    row = conn.execute("SELECT * FROM trade_summary_generations").fetchone()
    assert row["generation_status"] == "completed"
    assert json.loads(row["parser_versions_json"]) == ["stp_parser_v3"]
    assert json.loads(row["field_mapper_versions_json"]) == ["stp_field_mapper_v3"]
    assert "secret-token" not in json.dumps(dict(row), ensure_ascii=False)
    conn.close()


def test_generation_replaces_old_model_projection_with_current_model_artifact(tmp_path, monkeypatch):
    conn = connect(tmp_path / "current-model.db")
    initialize_database(conn)
    groups = _eligible_groups()
    monkeypatch.setattr(trade_summary_module, "_trade_summary_groups", lambda *_args, **_kwargs: groups)
    old_env = {**_configured_env(), "GRIT_REVIEW_LLM_MODEL": "local-review-model-old"}
    current_env = {**_configured_env(), "GRIT_REVIEW_LLM_MODEL": "local-review-model-current"}

    old_result = generate_trade_summary(
        conn,
        env=old_env,
        chat_client=lambda *_args: _valid_response(get_trade_summary(conn, env=old_env)),
    )
    assert old_result["generation"]["status"] == "completed"
    assert old_result["generation"]["model"] == "local-review-model-old"

    stale = get_trade_summary(conn, env=current_env)
    assert stale["generation"]["status"] == "stale"
    assert stale["generation"]["current_model"] == "local-review-model-current"
    assert stale["generation"]["model"] == "local-review-model-old"

    payload_models = []

    def current_client(_url, _headers, payload, _timeout):
        payload_models.append(payload["model"])
        return _valid_response(get_trade_summary(conn, env=current_env))

    current_result = generate_trade_summary(conn, env=current_env, chat_client=current_client)
    assert current_result["generation"]["status"] == "completed"
    assert current_result["generation"]["current_model"] == "local-review-model-current"
    assert current_result["generation"]["model"] == "local-review-model-current"
    assert payload_models == ["local-review-model-current"]
    assert conn.execute("SELECT COUNT(*) FROM trade_summary_generations").fetchone()[0] == 2
    conn.close()


def test_session_generated_summary_is_persisted_and_projected_without_local_llm(tmp_path, monkeypatch):
    conn = connect(tmp_path / "session-summary.db")
    initialize_database(conn)
    monkeypatch.setattr(trade_summary_module, "_trade_summary_groups", lambda *_args, **_kwargs: _eligible_groups())
    summary = get_trade_summary(conn, env={})
    narrative = json.loads(_valid_response(summary)["choices"][0]["message"]["content"])

    recorded = record_session_trade_summary(conn, narrative)
    reused = record_session_trade_summary(conn, narrative)

    assert recorded["generation"]["status"] == "completed"
    assert recorded["generation"]["provider"] == "codex_session"
    assert recorded["generation"]["model"] == "codex_current_session"
    assert recorded["generation"]["llm_configured"] is False
    assert recorded["generation"]["narrative"]["headline"] == narrative["headline"]
    assert reused["generation"]["artifact_id"] == recorded["generation"]["artifact_id"]
    assert conn.execute("SELECT COUNT(*) FROM trade_summary_generations").fetchone()[0] == 1
    conn.close()


def test_session_summary_is_hidden_when_evidence_changes(tmp_path, monkeypatch):
    conn = connect(tmp_path / "session-summary-stale.db")
    initialize_database(conn)
    groups = _eligible_groups()
    monkeypatch.setattr(trade_summary_module, "_trade_summary_groups", lambda *_args, **_kwargs: groups)
    summary = get_trade_summary(conn, env={})
    narrative = json.loads(_valid_response(summary)["choices"][0]["message"]["content"])
    recorded = record_session_trade_summary(conn, narrative)

    groups[0]["pnl"] = float(groups[0]["pnl"]) + 1
    stale = get_trade_summary(conn, env={})

    assert stale["summary_key"] != recorded["summary_key"]
    assert stale["generation"]["status"] == "stale"
    assert stale["generation"]["provider"] == "codex_session"
    assert stale["generation"]["narrative"] is None
    conn.close()


def test_failed_generation_retries_same_artifact_and_rejects_rule_id_tampering(tmp_path, monkeypatch):
    conn = connect(tmp_path / "retry.db")
    initialize_database(conn)
    groups = _eligible_groups()
    monkeypatch.setattr(trade_summary_module, "_trade_summary_groups", lambda *_args, **_kwargs: groups)

    def tampered_client(_url, _headers, _payload, _timeout):
        summary = get_trade_summary(conn, env=_configured_env())
        response = _valid_response(summary)
        decoded = json.loads(response["choices"][0]["message"]["content"])
        decoded["execution_rules"][0]["rule_id"] = "fabricated_rule"
        response["choices"][0]["message"]["content"] = json.dumps(decoded, ensure_ascii=False)
        return response

    failed = generate_trade_summary(conn, env=_configured_env(), chat_client=tampered_client)
    failed_id = failed["generation"]["artifact_id"]
    assert failed["generation"]["status"] == "failed"
    assert failed["generation"]["failure_reason"] == "trade_summary_llm_rule_id_mismatch"

    def valid_client(_url, _headers, _payload, _timeout):
        return _valid_response(get_trade_summary(conn, env=_configured_env()))

    completed = generate_trade_summary(conn, env=_configured_env(), chat_client=valid_client)
    assert completed["generation"]["status"] == "completed"
    assert completed["generation"]["artifact_id"] == failed_id
    assert completed["generation"]["retry_count"] == 1
    assert conn.execute("SELECT COUNT(*) FROM trade_summary_generations").fetchone()[0] == 1
    conn.close()


@pytest.mark.parametrize(
    ("failure_code", "client_factory"),
    [
        (
            "trade_summary_llm_timeout",
            lambda: (
                lambda _url, _headers, _payload, _timeout: (_ for _ in ()).throw(
                    trade_summary_module.TradeSummaryGenerationError("trade_summary_llm_timeout")
                )
            ),
        ),
        (
            "trade_summary_llm_unavailable",
            lambda: (
                lambda _url, _headers, _payload, _timeout: (_ for _ in ()).throw(
                    trade_summary_module.TradeSummaryGenerationError("trade_summary_llm_unavailable")
                )
            ),
        ),
        (
            "trade_summary_llm_http_error",
            lambda: (
                lambda _url, _headers, _payload, _timeout: (_ for _ in ()).throw(
                    trade_summary_module.TradeSummaryGenerationError("trade_summary_llm_http_error")
                )
            ),
        ),
        (
            "trade_summary_llm_invalid_json",
            lambda: (lambda _url, _headers, _payload, _timeout: {"choices": [{"message": {"content": "not-json"}}]}),
        ),
    ],
)
def test_generation_failure_modes_preserve_deterministic_rules(
    tmp_path, monkeypatch, failure_code, client_factory
):
    conn = connect(tmp_path / f"{failure_code}.db")
    initialize_database(conn)
    monkeypatch.setattr(trade_summary_module, "_trade_summary_groups", lambda *_args, **_kwargs: _eligible_groups())
    result = generate_trade_summary(conn, env=_configured_env(), chat_client=client_factory())
    assert result["generation"]["status"] == "failed"
    assert result["generation"]["failure_reason"] == failure_code
    assert result["execution_rules"]
    assert result["avoidance_rules"]
    conn.close()


def test_generation_rejects_new_numbers_in_model_wording(tmp_path, monkeypatch):
    conn = connect(tmp_path / "new-number.db")
    initialize_database(conn)
    monkeypatch.setattr(trade_summary_module, "_trade_summary_groups", lambda *_args, **_kwargs: _eligible_groups())

    def numbered_client(_url, _headers, _payload, _timeout):
        response = _valid_response(get_trade_summary(conn, env=_configured_env()))
        decoded = json.loads(response["choices"][0]["message"]["content"])
        decoded["overview"] = "建议新增百分之五十的交易结论 50%。"
        response["choices"][0]["message"]["content"] = json.dumps(decoded, ensure_ascii=False)
        return response

    result = generate_trade_summary(conn, env=_configured_env(), chat_client=numbered_client)
    assert result["generation"]["status"] == "failed"
    assert result["generation"]["failure_reason"] == "trade_summary_llm_new_number_rejected"
    conn.close()


@pytest.mark.parametrize(
    "base_url",
    ["https://example.com/v1", "http://192.168.1.8:11434/v1", "http://127.0.0.1:11434/api"],
)
def test_generation_rejects_non_loopback_or_non_v1_base_url(tmp_path, monkeypatch, base_url):
    conn = connect(tmp_path / "config.db")
    initialize_database(conn)
    monkeypatch.setattr(trade_summary_module, "_trade_summary_groups", lambda *_args, **_kwargs: _eligible_groups())
    with pytest.raises(ValueError):
        generate_trade_summary(conn, env=_configured_env(base_url))
    assert conn.execute("SELECT COUNT(*) FROM trade_summary_generations").fetchone()[0] == 0
    conn.close()


def test_api_exposes_contract_and_does_not_create_artifact_without_trades(tmp_path):
    database = tmp_path / "api.db"
    with TestClient(create_app(database)) as client:
        health = client.get("/api/healthz").json()
        assert health["trade_summary_contract"] == "trade_summary_contract_v3"
        assert "/api/review/trade-summary" in health["required_routes"]
        assert "/api/review/trade-summary/generations" in health["required_routes"]
        summary = client.get("/api/review/trade-summary").json()
        assert summary["evidence_status"] == "no_trades"
        assert summary["generation"]["status"] == "unconfigured"
        response = client.post("/api/review/trade-summary/generations", json={})
        assert response.status_code == 422
    conn = connect(database)
    assert conn.execute("SELECT COUNT(*) FROM trade_summary_generations").fetchone()[0] == 0
    conn.close()


@pytest.mark.parametrize(
    ("evidence_status", "generation_status"),
    [("fabricated", "pending"), ("eligible", "fabricated")],
)
def test_v9_generation_table_rejects_unknown_statuses(tmp_path, evidence_status, generation_status):
    conn = connect(tmp_path / "constraints.db")
    initialize_database(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO trade_summary_generations (
                id, summary_key, idempotency_key, evidence_status, generation_status,
                rule_catalog_version, prompt_version, provider, model, model_config_hash,
                evidence_snapshot_json, deterministic_rules_json
            ) VALUES ('artifact', 'summary', 'idem', ?, ?, 'catalog', 'prompt',
                      'provider', 'model', 'config', '{}', '{}')
            """,
            (evidence_status, generation_status),
        )
    conn.close()
