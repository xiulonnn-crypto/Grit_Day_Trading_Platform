from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from grit_day_trading.ai_strategy import AI_STRATEGY_CATALOG, get_ai_strategy_recommendations
from grit_day_trading.storage import connect, initialize_database
from grit_day_trading.strategy import list_strategy_configs, run_strategy_test_batch, update_strategy_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the versioned AI strategy benchmark from saved minute archives.")
    parser.add_argument("--db", default="data/grit_day_trading.db", help="SQLite database path.")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Benchmark end date (YYYY-MM-DD).")
    parser.add_argument("--symbols", default="MU", help="Comma-separated archived symbols.")
    parser.add_argument("--window-calendar-days", type=int, default=30, help="Natural-day archive window.")
    parser.add_argument("--provider", default="yahoo", help="Saved archive provider.")
    parser.add_argument("--force", action="store_true", help="Replace matching run artifacts before rebuilding batches.")
    parser.add_argument(
        "--report",
        default="output/logs/grit-coder/ai-strategy-v2/benchmark-report.json",
        help="Local benchmark manifest path.",
    )
    return parser.parse_args()


def canonical_symbols(raw: str) -> list[str]:
    symbols = sorted({item.strip().upper() for item in raw.split(",") if item.strip()})
    if not symbols:
        raise ValueError("strategy_symbol_required")
    return symbols


def main() -> int:
    args = parse_args()
    symbols = canonical_symbols(args.symbols)
    conn = connect(args.db)
    initialize_database(conn)
    template_keys = [entry["template_key"] for entry in AI_STRATEGY_CATALOG]
    configs = {config["template_key"]: config for config in list_strategy_configs(conn)}
    missing_configs = [key for key in template_keys if key not in configs]
    if missing_configs:
        raise RuntimeError("missing_strategy_configs:" + ",".join(missing_configs))
    original_enabled = {
        configs[key]["strategy_id"]: bool(configs[key]["enabled"])
        for key in template_keys
    }
    batches: list[dict[str, object]] = []
    try:
        for template_key in template_keys:
            config = configs[template_key]
            if not config["enabled"]:
                update_strategy_config(conn, config["strategy_id"], enabled=True)
            for symbol in symbols:
                batch = run_strategy_test_batch(
                    conn,
                    strategy_id=config["strategy_id"],
                    provider=args.provider,
                    symbol=symbol,
                    end_date=args.end_date,
                    window_trading_days=args.window_calendar_days,
                    force=args.force,
                )
                batches.append(
                    {
                        "batch_id": batch["batch_id"],
                        "strategy_id": batch["strategy_id"],
                        "template_key": batch["template_key"],
                        "symbol": batch["symbol"],
                        "status": batch["status"],
                        "archive_scope_hash": batch["archive_scope_hash"],
                        "params_hash": batch["params_hash"],
                        "completed_day_count": batch["completed_day_count"],
                        "signal_count": batch["signal_count"],
                        "total_pnl": batch["total_pnl"],
                        "win_rate": batch["win_rate"],
                        "profit_factor": batch["profit_factor"],
                        "max_drawdown": batch["max_drawdown"],
                    }
                )
    finally:
        for strategy_id, enabled in original_enabled.items():
            current = next(
                (config for config in list_strategy_configs(conn) if config["strategy_id"] == strategy_id),
                None,
            )
            if current is not None and bool(current["enabled"]) != enabled:
                update_strategy_config(conn, strategy_id, enabled=enabled)

    recommendations = get_ai_strategy_recommendations(
        conn,
        end_date=args.end_date,
        symbols=symbols,
        window_calendar_days=args.window_calendar_days,
    )
    scope = {
        "end_date": args.end_date,
        "symbols": symbols,
        "window_calendar_days": args.window_calendar_days,
        "initial_capital": recommendations["initial_capital"],
        "entry_capital_ratio": recommendations["entry_capital_ratio"],
    }
    ranking = [
        {
            "rank": item["rank"],
            "template_key": item["template_key"],
            "strategy_name": item["strategy_name"],
            "expected_pnl_per_closed_trade": item["expectation"]["expected_pnl_per_closed_trade"],
            "total_pnl": item["expectation"]["total_pnl"],
            "win_rate": item["expectation"]["win_rate"],
            "profit_factor": item["expectation"]["profit_factor"],
            "max_drawdown": item["expectation"]["max_drawdown"],
            "completed_day_count": item["expectation"]["completed_day_count"],
            "closed_group_count": item["expectation"]["closed_group_count"],
            "excluded_day_count": item["expectation"]["excluded_day_count"],
            "matching_batch_ids": item["expectation"]["matching_batch_ids"],
            "archive_scope_hashes": item["expectation"]["archive_scope_hashes"],
        }
        for item in recommendations["items"]
    ]
    stable_payload = {
        "catalog_version": recommendations["catalog_version"],
        "ranking_version": recommendations["ranking_version"],
        "ranking_basis": recommendations["ranking_basis"],
        "evidence_status": recommendations["evidence_status"],
        "scope": scope,
        "batches": batches,
        "ranking": ranking,
        "recommendation_key": recommendations["recommendation_key"],
    }
    artifact_hash = hashlib.sha256(
        json.dumps(stable_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    source_scope_hash = hashlib.sha256(
        "|".join(sorted(str(batch["batch_id"]) for batch in batches)).encode("utf-8")
    ).hexdigest()
    report = {
        "manifest_version": "ai_strategy_benchmark_manifest_v1",
        "job_id": f"aibench_{artifact_hash[:20]}",
        "source_job_id": f"strattestscope_{source_scope_hash[:20]}",
        "artifact_id": f"aibenchartifact_{artifact_hash[:20]}",
        "formula_count": len(template_keys),
        "result_count": len(ranking),
        "hash": artifact_hash,
        "generated_at": datetime.now(UTC).isoformat(),
        **stable_payload,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, separators=(",", ":")))
    conn.close()
    return 0 if recommendations["ranking_basis"] == "local_backtest" else 2


if __name__ == "__main__":
    raise SystemExit(main())
