from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "review-snapshot.json"


def fetch_json(base_url: str, path: str) -> dict[str, Any]:
    url = urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))
    with urlopen(url, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError(f"snapshot source returned HTTP {response.status}: {path}")
        return json.load(response)


def project_trade_group(group: dict[str, Any]) -> dict[str, Any]:
    drawdown = group.get("position_drawdown") or {}
    evaluation = group.get("evaluation") or {}
    review = group.get("review") or {}
    return {
        "symbol": group.get("symbol"),
        "direction": group.get("direction"),
        "status": group.get("status"),
        "opened_at": group.get("opened_at"),
        "closed_at": group.get("closed_at"),
        "holding_minutes": group.get("holding_minutes"),
        "fill_count": group.get("fill_count"),
        "total_quantity": group.get("total_quantity"),
        "avg_entry_price": group.get("avg_entry_price"),
        "avg_exit_price": group.get("avg_exit_price"),
        "pnl": group.get("pnl"),
        "position_drawdown": {
            "status": drawdown.get("status"),
            "max_drawdown": drawdown.get("max_drawdown"),
            "entry_atr_multiple": drawdown.get("entry_atr_multiple"),
            "entry_atr_regime": drawdown.get("entry_atr_regime"),
        },
        "evaluation": {
            "evaluation_status": evaluation.get("evaluation_status"),
            "grade": evaluation.get("grade"),
        },
        "review": (
            {
                "reason_category": review.get("reason_category"),
                "reason_code": review.get("reason_code"),
            }
            if review
            else None
        ),
    }


def project_trade_summary(payload: dict[str, Any]) -> dict[str, Any]:
    projected = json.loads(json.dumps(payload, ensure_ascii=False))
    projected.pop("summary_key", None)
    generation = projected.get("generation")
    if isinstance(generation, dict):
        generation.pop("artifact_id", None)
        generation.pop("artifact_summary_key", None)
    return projected


def stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_snapshot(core: dict[str, Any]) -> None:
    summary = core["summary"]
    groups = [
        group
        for group in core["trade_groups"]
        if group["status"] == "closed" and group["pnl"] is not None
    ]
    projected_count = len(groups)
    projected_quantity = sum(int(group["total_quantity"] or 0) for group in groups)
    projected_pnl = sum(float(group["pnl"] or 0) for group in groups)

    if projected_count != int(summary["trade_group_count"]):
        raise RuntimeError(
            f"trade group count mismatch: projected={projected_count}, "
            f"summary={summary['trade_group_count']}"
        )
    if projected_quantity != int(summary["traded_quantity"]):
        raise RuntimeError(
            f"traded quantity mismatch: projected={projected_quantity}, "
            f"summary={summary['traded_quantity']}"
        )
    if abs(projected_pnl - float(summary["pnl"])) > 0.000001:
        raise RuntimeError(
            f"PnL mismatch: projected={projected_pnl}, summary={summary['pnl']}"
        )

    serialized = json.dumps(core, ensure_ascii=False)
    forbidden_tokens = (
        "account_raw",
        "account_canonical",
        "raw_line",
        "raw_line_numbers",
        "source_batch_ids",
        "idempotency_key",
        "artifact_id",
    )
    leaked = [token for token in forbidden_tokens if token in serialized]
    if leaked:
        raise RuntimeError(f"snapshot contains forbidden private fields: {', '.join(leaked)}")


def build_snapshot(base_url: str) -> dict[str, Any]:
    trade_groups_payload = fetch_json(
        base_url, "/api/trade-groups?include_details=false"
    )
    summary = fetch_json(base_url, "/api/review/summary")
    date_groups = fetch_json(
        base_url, "/api/review/summary-groups?group_by=date"
    ).get("items", [])
    symbol_groups = fetch_json(
        base_url, "/api/review/summary-groups?group_by=symbol"
    ).get("items", [])
    trade_summary = project_trade_summary(
        fetch_json(base_url, "/api/review/trade-summary")
    )

    projected_groups = [
        project_trade_group(group) for group in trade_groups_payload.get("items", [])
    ]
    latest_date = max(
        (item.get("group_key", "") for item in date_groups),
        default="",
    )
    core = {
        "schema_version": "github_pages_review_snapshot_v1",
        "as_of_date": latest_date or None,
        "summary": summary,
        "date_groups": date_groups,
        "symbol_groups": symbol_groups,
        "trade_groups": projected_groups,
        "trade_summary": trade_summary,
    }
    validate_snapshot(core)
    return {
        **core,
        "exported_at": datetime.now(UTC).isoformat(),
        "source_hash": stable_hash(core),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export the local review read model for the GitHub Pages snapshot."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:5173",
        help="Local frontend or backend base URL.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Snapshot JSON output path.",
    )
    args = parser.parse_args()

    snapshot = build_snapshot(args.base_url)
    output = args.output.resolve()
    if ROOT not in output.parents and output != ROOT:
        raise RuntimeError(f"output must stay inside the repository: {output}")
    output.write_text(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output.relative_to(ROOT)),
                "source_hash": snapshot["source_hash"],
                "as_of_date": snapshot["as_of_date"],
                "trade_group_count": snapshot["summary"]["trade_group_count"],
                "traded_quantity": snapshot["summary"]["traded_quantity"],
                "pnl": snapshot["summary"]["pnl"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
