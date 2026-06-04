from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from .futu_provider import FutuMarketDataProvider
from .market_provider import FakeMarketDataProvider, MarketBar, MarketDataProvider, MinuteBarResponse
from .storage import dumps_json, new_id, row_to_dict
from .yahoo_provider import YahooFinanceMarketDataProvider


def replay_market_context(
    conn: sqlite3.Connection,
    *,
    fill_id: str,
    provider_name: str = "fake",
    minutes_before: int = 30,
    minutes_after: int = 30,
    force: bool = False,
    provider: MarketDataProvider | None = None,
) -> dict[str, Any]:
    if minutes_before < 1 or minutes_after < 1:
        raise ValueError("invalid_window")
    fill = _get_fill(conn, fill_id)
    filled_at = _parse_fill_time(fill["filled_at"])
    requested_start = _format_iso(filled_at - timedelta(minutes=minutes_before))
    requested_end = _format_iso(filled_at + timedelta(minutes=minutes_after))
    provider_key = provider_name.strip().lower() or "fake"

    existing = conn.execute(
        """
        SELECT * FROM market_context_snapshots
        WHERE fill_id = ? AND provider = ? AND requested_start = ? AND requested_end = ?
        """,
        (fill_id, provider_key, requested_start, requested_end),
    ).fetchone()
    if existing and not force:
        return _public_snapshot(existing)

    selected_provider = provider or resolve_provider(provider_key)
    response = selected_provider.fetch_minute_bars(fill["symbol"], requested_start, requested_end)
    attempt_status = _provider_attempt_status(response.status)
    bars_json = _bars_json(response.bars)
    payload_hash = _sha256_text(bars_json if response.bars else (response.error_code or response.status))
    with conn:
        conn.execute(
            """
            INSERT INTO market_data_provider_attempts (
                id, provider, symbol, request_type, requested_start, requested_end,
                status, error_code, payload_hash, created_at
            ) VALUES (?, ?, ?, 'minute_bars', ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("attempt"),
                provider_key,
                fill["symbol"],
                requested_start,
                requested_end,
                attempt_status,
                response.error_code,
                payload_hash,
                _now(),
            ),
        )
        snapshot_payload = _snapshot_payload(fill, provider_key, requested_start, requested_end, response)
        if existing:
            snapshot_id = existing["id"]
            conn.execute(
                """
                UPDATE market_context_snapshots
                SET symbol = ?, provider_timezone = ?, bar_count = ?, bars_hash = ?, bars_json = ?,
                    vwap = ?, day_high = ?, day_low = ?, volume_context = ?, data_status = ?,
                    failure_reason = ?, created_at = ?
                WHERE id = ?
                """,
                (
                    snapshot_payload["symbol"],
                    snapshot_payload["provider_timezone"],
                    snapshot_payload["bar_count"],
                    snapshot_payload["bars_hash"],
                    snapshot_payload["bars_json"],
                    snapshot_payload["vwap"],
                    snapshot_payload["day_high"],
                    snapshot_payload["day_low"],
                    snapshot_payload["volume_context"],
                    snapshot_payload["data_status"],
                    snapshot_payload["failure_reason"],
                    snapshot_payload["created_at"],
                    snapshot_id,
                ),
            )
        else:
            snapshot_id = new_id("mctx")
            conn.execute(
                """
                INSERT INTO market_context_snapshots (
                    id, fill_id, provider, symbol, requested_start, requested_end,
                    provider_timezone, bar_count, bars_hash, bars_json, vwap, day_high, day_low,
                    volume_context, data_status, failure_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    fill_id,
                    provider_key,
                    snapshot_payload["symbol"],
                    requested_start,
                    requested_end,
                    snapshot_payload["provider_timezone"],
                    snapshot_payload["bar_count"],
                    snapshot_payload["bars_hash"],
                    snapshot_payload["bars_json"],
                    snapshot_payload["vwap"],
                    snapshot_payload["day_high"],
                    snapshot_payload["day_low"],
                    snapshot_payload["volume_context"],
                    snapshot_payload["data_status"],
                    snapshot_payload["failure_reason"],
                    snapshot_payload["created_at"],
                ),
            )

    return get_market_context_snapshot(conn, snapshot_id)


def get_market_context_for_fill(conn: sqlite3.Connection, fill_id: str) -> dict[str, Any]:
    _get_fill(conn, fill_id)
    row = conn.execute(
        """
        SELECT * FROM market_context_snapshots
        WHERE fill_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (fill_id,),
    ).fetchone()
    if not row:
        raise KeyError("market_context_not_found")
    return _public_snapshot(row)


def get_market_context_snapshot(conn: sqlite3.Connection, snapshot_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM market_context_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
    if not row:
        raise KeyError("market_context_not_found")
    return _public_snapshot(row)


def resolve_provider(provider_name: str) -> MarketDataProvider:
    if provider_name == "futu":
        return FutuMarketDataProvider()
    if provider_name == "yahoo":
        return YahooFinanceMarketDataProvider()
    return FakeMarketDataProvider()


def _get_fill(conn: sqlite3.Connection, fill_id: str) -> dict[str, Any]:
    fill = row_to_dict(conn.execute("SELECT * FROM fills WHERE id = ?", (fill_id,)).fetchone())
    if not fill:
        raise KeyError("fill_not_found")
    return fill


def _snapshot_payload(
    fill: dict[str, Any],
    provider: str,
    requested_start: str,
    requested_end: str,
    response: MinuteBarResponse,
) -> dict[str, Any]:
    bars = [bar.as_dict() for bar in response.bars]
    bars_json = json.dumps(bars, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    bars_hash = _sha256_text(bars_json)
    expected = _expected_bar_count(requested_start, requested_end)
    data_status = _data_status(response, expected)
    metrics = _bar_metrics(response.bars) if response.bars else {"vwap": None, "day_high": None, "day_low": None}
    volume_context = _volume_context(response.bars, expected)
    failure_reason = _failure_reason(response, data_status)
    return {
        "provider": provider,
        "symbol": fill["symbol"],
        "provider_timezone": response.provider_timezone,
        "bar_count": len(response.bars),
        "bars_hash": bars_hash,
        "bars_json": bars_json,
        "vwap": metrics["vwap"],
        "day_high": metrics["day_high"],
        "day_low": metrics["day_low"],
        "volume_context": dumps_json(volume_context),
        "data_status": data_status,
        "failure_reason": failure_reason,
        "created_at": _now(),
    }


def _data_status(response: MinuteBarResponse, expected_bar_count: int) -> str:
    if response.status == "provider_failed":
        return "provider_failed"
    if response.status == "timezone_conflict":
        return "timezone_conflict"
    if response.status == "missing" or not response.bars:
        return "missing"
    if response.status == "partial" or len(response.bars) < expected_bar_count:
        return "partial"
    return "available"


def _bar_metrics(bars: list[MarketBar]) -> dict[str, float | None]:
    total_volume = sum(float(bar.volume) for bar in bars)
    vwap = None if total_volume <= 0 else sum(float(bar.close) * float(bar.volume) for bar in bars) / total_volume
    return {
        "vwap": None if vwap is None else round(vwap, 6),
        "day_high": round(max(float(bar.high) for bar in bars), 6),
        "day_low": round(min(float(bar.low) for bar in bars), 6),
    }


def _volume_context(bars: list[MarketBar], expected_bar_count: int) -> dict[str, Any]:
    total_volume = sum(float(bar.volume) for bar in bars)
    avg_bar_volume = 0.0 if not bars else total_volume / len(bars)
    return {
        "bar_count": len(bars),
        "expected_bar_count": expected_bar_count,
        "total_volume": round(total_volume, 6),
        "avg_bar_volume": round(avg_bar_volume, 6),
    }


def _failure_reason(response: MinuteBarResponse, data_status: str) -> str | None:
    if data_status == "available":
        return None
    if response.error_code:
        return response.error_code
    if data_status == "partial":
        return "partial_provider_window"
    if data_status == "missing":
        return "no_bars_returned"
    if data_status == "timezone_conflict":
        return "provider_timezone_conflict"
    return "provider_failed"


def _provider_attempt_status(data_status: str) -> str:
    return {
        "available": "success",
        "partial": "partial",
        "missing": "missing",
        "provider_failed": "failed",
        "timezone_conflict": "timezone_conflict",
    }.get(data_status, "failed")


def _bars_json(bars: list[MarketBar]) -> str:
    return json.dumps([bar.as_dict() for bar in bars], ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _expected_bar_count(requested_start: str, requested_end: str) -> int:
    start = _parse_fill_time(requested_start)
    end = _parse_fill_time(requested_end)
    return int((end - start).total_seconds() // 60) + 1


def _parse_fill_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _format_iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _public_snapshot(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["snapshot_id"] = payload["id"]
    payload["bar_count"] = int(payload["bar_count"])
    payload["bars"] = json.loads(payload["bars_json"])
    payload["volume_context"] = json.loads(payload["volume_context"])
    for key in ("vwap", "day_high", "day_low"):
        payload[key] = None if payload[key] is None else float(payload[key])
    return payload
