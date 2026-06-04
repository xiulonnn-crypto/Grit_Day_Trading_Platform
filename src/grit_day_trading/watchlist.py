from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from .futu_provider import FutuMarketDataProvider
from .market_provider import FakeMarketDataProvider, MarketDataProvider, WatchlistCandidate
from .storage import dumps_json, new_id


WATCHLIST_RULES_VERSION = "watchlist_rules_v1"


def generate_watchlist(
    conn: sqlite3.Connection,
    *,
    trade_date: str,
    provider_name: str = "fake",
    force: bool = False,
    provider: MarketDataProvider | None = None,
) -> dict[str, Any]:
    provider_key = provider_name.strip().lower() or "fake"
    existing = _find_run(conn, trade_date, provider_key)
    if existing and not force:
        return get_watchlist(conn, trade_date, provider=provider_key)

    selected_provider = provider or resolve_provider(provider_key)
    response = selected_provider.fetch_watchlist_candidates(trade_date)
    run_id = existing["id"] if existing else new_id("watchrun")
    status = "failed" if response.status == "provider_failed" else "completed"
    failure_reason = response.error_code if status == "failed" else None
    items = [] if status == "failed" else _rank_candidates(response.candidates)

    with conn:
        if existing:
            conn.execute("DELETE FROM watchlist_items WHERE run_id = ?", (run_id,))
            conn.execute(
                """
                UPDATE watchlist_runs
                SET status = ?, item_count = ?, failure_reason = ?, created_at = ?
                WHERE id = ?
                """,
                (status, len(items), failure_reason, _now(), run_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO watchlist_runs (
                    id, trade_date, provider, rules_version, status, item_count, failure_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, trade_date, provider_key, WATCHLIST_RULES_VERSION, status, len(items), failure_reason, _now()),
            )
        for item in items:
            conn.execute(
                """
                INSERT INTO watchlist_items (
                    id, run_id, trade_date, symbol, rank, reason_codes_json,
                    metrics_json, source, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("watchitem"),
                    run_id,
                    trade_date,
                    item["symbol"],
                    item["rank"],
                    dumps_json({"codes": item["reason_codes"]}),
                    dumps_json(item["metrics"]),
                    item["source"],
                    item["status"],
                ),
            )

    return get_watchlist(conn, trade_date, provider=provider_key)


def get_watchlist(conn: sqlite3.Connection, trade_date: str, *, provider: str | None = None) -> dict[str, Any]:
    if provider:
        run = _find_run(conn, trade_date, provider.strip().lower())
    else:
        run = conn.execute(
            """
            SELECT * FROM watchlist_runs
            WHERE trade_date = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (trade_date,),
        ).fetchone()
    if not run:
        return {
            "id": None,
            "run_id": None,
            "trade_date": trade_date,
            "provider": provider,
            "rules_version": WATCHLIST_RULES_VERSION,
            "status": "not_generated",
            "item_count": 0,
            "failure_reason": None,
            "created_at": None,
            "items": [],
        }
    items = conn.execute(
        """
        SELECT * FROM watchlist_items
        WHERE run_id = ?
        ORDER BY rank, symbol
        """,
        (run["id"],),
    ).fetchall()
    return _public_run(run, items)


def resolve_provider(provider_name: str) -> MarketDataProvider:
    if provider_name == "futu":
        return FutuMarketDataProvider()
    return FakeMarketDataProvider()


def _find_run(conn: sqlite3.Connection, trade_date: str, provider: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM watchlist_runs
        WHERE trade_date = ? AND provider = ? AND rules_version = ?
        """,
        (trade_date, provider, WATCHLIST_RULES_VERSION),
    ).fetchone()


def _rank_candidates(candidates: list[WatchlistCandidate]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        symbol = candidate.symbol.strip().upper()
        if not symbol:
            continue
        reason_codes = _reason_codes(candidate.metrics)
        if not reason_codes:
            continue
        scored.append(
            {
                "symbol": symbol,
                "reason_codes": reason_codes,
                "metrics": {key: float(value) for key, value in candidate.metrics.items()},
                "source": candidate.source,
                "status": candidate.status if candidate.status in {"included", "missing", "provider_failed"} else "included",
                "_score": _score(candidate.metrics),
            }
        )
    scored.sort(key=lambda item: (-item["_score"], item["symbol"]))
    for index, item in enumerate(scored, start=1):
        item["rank"] = index
        del item["_score"]
    return scored


def _reason_codes(metrics: dict[str, float]) -> list[str]:
    reasons: list[str] = []
    if float(metrics.get("relative_volume", 0.0)) >= 1.5:
        reasons.append("relative_volume_spike")
    gap = float(metrics.get("gap_percent", 0.0))
    if gap >= 2.0:
        reasons.append("gap_up")
    if gap <= -2.0:
        reasons.append("gap_down")
    if float(metrics.get("price_change_percent", 0.0)) >= 3.0:
        reasons.append("momentum")
    return reasons


def _score(metrics: dict[str, float]) -> float:
    return (
        float(metrics.get("relative_volume", 0.0)) * 10
        + abs(float(metrics.get("gap_percent", 0.0))) * 2
        + float(metrics.get("price_change_percent", 0.0))
    )


def _public_run(run: sqlite3.Row, item_rows: list[sqlite3.Row]) -> dict[str, Any]:
    payload = dict(run)
    payload["run_id"] = payload["id"]
    payload["item_count"] = int(payload["item_count"])
    payload["items"] = [_public_item(row) for row in item_rows]
    return payload


def _public_item(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["item_id"] = payload["id"]
    payload["rank"] = int(payload["rank"])
    payload["reason_codes"] = json.loads(payload["reason_codes_json"])["codes"]
    payload["metrics"] = json.loads(payload["metrics_json"])
    payload["metrics_hash"] = hashlib.sha256(payload["metrics_json"].encode("utf-8")).hexdigest()
    return payload


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
