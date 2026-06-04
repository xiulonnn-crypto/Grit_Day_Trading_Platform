from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .market_provider import MarketBar, MarketDataProvider, MinuteBarResponse
from .service import list_fills
from .storage import dumps_json, new_id
from .strategy import MOMENTUM_CONTEXT_SYMBOLS, MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY
from .yahoo_provider import YahooFinanceMarketDataProvider


YAHOO_ARCHIVE_PROVIDER = "yahoo"
MARKET_MINUTE_ARCHIVE_VERSION = "market_minute_archive_v1"
REGULAR_SESSION_START = "04:00:00"
REGULAR_SESSION_END = "20:00:00"


def archive_yahoo_minutes_for_committed_fills(
    conn: sqlite3.Connection,
    *,
    trade_date: str | None = None,
    force: bool = False,
    provider: MarketDataProvider | None = None,
) -> dict[str, Any]:
    targets = _archive_targets(conn, trade_date=trade_date)
    items = [
        archive_market_minutes(
            conn,
            symbol=target["symbol"],
            trade_date=target["trade_date"],
            source_fill_count=target["source_fill_count"],
            provider_name=YAHOO_ARCHIVE_PROVIDER,
            force=force,
            provider=provider,
        )
        for target in targets
    ]
    return {
        "status": "no_targets" if not targets else "completed",
        "provider": YAHOO_ARCHIVE_PROVIDER,
        "archive_version": MARKET_MINUTE_ARCHIVE_VERSION,
        "trade_date": trade_date,
        "target_count": len(targets),
        "stored_count": len(items),
        "available_count": sum(1 for item in items if item["data_status"] == "available"),
        "non_available_count": sum(1 for item in items if item["data_status"] != "available"),
        "provider_failed_count": sum(1 for item in items if item["data_status"] == "provider_failed"),
        "items": items,
    }


def archive_yahoo_minutes_for_symbol_window(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    end_date: str,
    window_trading_days: int = 30,
    force: bool = False,
    provider: MarketDataProvider | None = None,
) -> dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        raise ValueError("archive_symbol_required")
    window = int(window_trading_days)
    if window < 1 or window > 30:
        raise ValueError("archive_window_trading_days_out_of_range")

    trade_dates = _recent_weekday_dates(end_date, window)
    target_symbols = [canonical_symbol]
    if _has_enabled_momentum_mean_reversion_strategy(conn):
        for context_symbol in MOMENTUM_CONTEXT_SYMBOLS:
            if context_symbol not in target_symbols:
                target_symbols.append(context_symbol)

    targets = [
        {
            "trade_date": target_date,
            "symbol": target_symbol,
            "source_fill_count": _source_fill_count(conn, trade_date=target_date, symbol=target_symbol),
        }
        for target_date in trade_dates
        for target_symbol in target_symbols
    ]
    items = [
        archive_market_minutes(
            conn,
            symbol=target["symbol"],
            trade_date=target["trade_date"],
            source_fill_count=target["source_fill_count"],
            provider_name=YAHOO_ARCHIVE_PROVIDER,
            force=force,
            provider=provider,
        )
        for target in targets
    ]
    selected_items = [item for item in items if item["symbol"] == canonical_symbol]
    return {
        "status": "completed",
        "provider": YAHOO_ARCHIVE_PROVIDER,
        "archive_version": MARKET_MINUTE_ARCHIVE_VERSION,
        "trade_date": end_date,
        "symbol": canonical_symbol,
        "window_trading_days": window,
        "requested_trade_dates": trade_dates,
        "target_count": len(targets),
        "stored_count": len(items),
        "available_count": sum(1 for item in items if item["data_status"] == "available"),
        "non_available_count": sum(1 for item in items if item["data_status"] != "available"),
        "provider_failed_count": sum(1 for item in items if item["data_status"] == "provider_failed"),
        "selected_symbol_available_count": sum(1 for item in selected_items if item["data_status"] == "available"),
        "items": items,
    }


def archive_market_minutes(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    trade_date: str,
    source_fill_count: int,
    provider_name: str = YAHOO_ARCHIVE_PROVIDER,
    force: bool = False,
    provider: MarketDataProvider | None = None,
) -> dict[str, Any]:
    provider_key = provider_name.strip().lower() or YAHOO_ARCHIVE_PROVIDER
    canonical_symbol = symbol.strip().upper()
    requested_start = f"{trade_date}T{REGULAR_SESSION_START}"
    requested_end = f"{trade_date}T{REGULAR_SESSION_END}"
    idempotency_key = _idempotency_key(provider_key, canonical_symbol, trade_date, requested_start, requested_end)
    existing = _find_archive(conn, idempotency_key)
    if existing and not force:
        _refresh_source_fill_count(conn, idempotency_key, source_fill_count)
        return get_market_minute_archive(conn, existing["id"])

    selected_provider = provider or resolve_provider(provider_key)
    response = selected_provider.fetch_minute_bars(canonical_symbol, requested_start, requested_end)
    bars_json = _bars_json(response.bars)
    bars_hash = _sha256_text(bars_json)
    payload_hash = _sha256_text(bars_json if response.bars else (response.error_code or response.status))
    data_status = _data_status(response)
    metrics = _bar_metrics(response.bars) if response.bars else {"vwap": None, "day_high": None, "day_low": None}
    volume_context = _volume_context(response.bars, requested_start, requested_end)
    failure_reason = _failure_reason(response, data_status)
    created_at = _now()

    with conn:
        conn.execute(
            """
            INSERT INTO market_data_provider_attempts (
                id, provider, symbol, request_type, requested_start, requested_end,
                status, error_code, payload_hash, created_at
            ) VALUES (?, ?, ?, 'archive_minute_bars', ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("attempt"),
                provider_key,
                canonical_symbol,
                requested_start,
                requested_end,
                _provider_attempt_status(data_status),
                response.error_code,
                payload_hash,
                created_at,
            ),
        )
        if existing:
            archive_id = existing["id"]
            conn.execute(
                """
                UPDATE market_minute_archives
                SET provider_timezone = ?, bar_count = ?, bars_hash = ?, bars_json = ?,
                    vwap = ?, day_high = ?, day_low = ?, volume_context = ?, data_status = ?,
                    failure_reason = ?, source_fill_count = ?, archive_version = ?, created_at = ?
                WHERE id = ?
                """,
                (
                    response.provider_timezone,
                    len(response.bars),
                    bars_hash,
                    bars_json,
                    metrics["vwap"],
                    metrics["day_high"],
                    metrics["day_low"],
                    dumps_json(volume_context),
                    data_status,
                    failure_reason,
                    int(source_fill_count),
                    MARKET_MINUTE_ARCHIVE_VERSION,
                    created_at,
                    archive_id,
                ),
            )
        else:
            archive_id = new_id("minbar")
            conn.execute(
                """
                INSERT INTO market_minute_archives (
                    id, provider, symbol, trade_date, requested_start, requested_end,
                    provider_timezone, bar_count, bars_hash, bars_json, vwap, day_high, day_low,
                    volume_context, data_status, failure_reason, source_fill_count,
                    archive_version, idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    archive_id,
                    provider_key,
                    canonical_symbol,
                    trade_date,
                    requested_start,
                    requested_end,
                    response.provider_timezone,
                    len(response.bars),
                    bars_hash,
                    bars_json,
                    metrics["vwap"],
                    metrics["day_high"],
                    metrics["day_low"],
                    dumps_json(volume_context),
                    data_status,
                    failure_reason,
                    int(source_fill_count),
                    MARKET_MINUTE_ARCHIVE_VERSION,
                    idempotency_key,
                    created_at,
                ),
            )

    return get_market_minute_archive(conn, archive_id)


def list_market_minute_archives(
    conn: sqlite3.Connection,
    *,
    trade_date: str | None = None,
    symbol: str | None = None,
    provider: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if trade_date:
        clauses.append("trade_date = ?")
        params.append(trade_date)
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol.strip().upper())
    if provider:
        clauses.append("provider = ?")
        params.append(provider.strip().lower())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT * FROM market_minute_archives
        {where}
        ORDER BY trade_date DESC, symbol, provider
        """,
        params,
    ).fetchall()
    return [_public_archive(row) for row in rows]


def get_market_minute_archive(conn: sqlite3.Connection, archive_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM market_minute_archives WHERE id = ?", (archive_id,)).fetchone()
    if not row:
        raise KeyError("market_minute_archive_not_found")
    return _public_archive(row)


def resolve_provider(provider_name: str) -> MarketDataProvider:
    if provider_name == YAHOO_ARCHIVE_PROVIDER:
        return YahooFinanceMarketDataProvider()
    raise ValueError("unsupported_archive_provider")


def _archive_targets(conn: sqlite3.Connection, *, trade_date: str | None) -> list[dict[str, Any]]:
    fills = list_fills(conn, date=trade_date)
    counts: dict[tuple[str, str], int] = {}
    for fill in fills:
        key = (str(fill["filled_at"])[:10], str(fill["symbol"]).strip().upper())
        counts[key] = counts.get(key, 0) + 1
    if _has_enabled_momentum_mean_reversion_strategy(conn):
        target_dates = {trade_date} if trade_date else {target_trade_date for target_trade_date, _ in counts}
        for target_trade_date in sorted(date for date in target_dates if date):
            for symbol in MOMENTUM_CONTEXT_SYMBOLS:
                counts.setdefault((target_trade_date, symbol), 0)
    return [
        {"trade_date": target_trade_date, "symbol": symbol, "source_fill_count": count}
        for (target_trade_date, symbol), count in sorted(counts.items())
    ]


def _source_fill_count(conn: sqlite3.Connection, *, trade_date: str, symbol: str) -> int:
    canonical_symbol = symbol.strip().upper()
    return sum(1 for fill in list_fills(conn, date=trade_date) if str(fill["symbol"]).strip().upper() == canonical_symbol)


def _recent_weekday_dates(end_date: str, window_trading_days: int) -> list[str]:
    try:
        current = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("archive_end_date_invalid") from exc

    dates: list[str] = []
    while len(dates) < window_trading_days:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current -= timedelta(days=1)
    return list(reversed(dates))


def _has_enabled_momentum_mean_reversion_strategy(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM strategy_configs
        WHERE template_key = ? AND enabled = 1
        LIMIT 1
        """,
        (MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY,),
    ).fetchone()
    return row is not None


def _find_archive(conn: sqlite3.Connection, idempotency_key: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM market_minute_archives WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()


def _refresh_source_fill_count(conn: sqlite3.Connection, idempotency_key: str, source_fill_count: int) -> None:
    with conn:
        conn.execute(
            "UPDATE market_minute_archives SET source_fill_count = ? WHERE idempotency_key = ?",
            (int(source_fill_count), idempotency_key),
        )


def _data_status(response: MinuteBarResponse) -> str:
    if response.status == "provider_failed":
        return "provider_failed"
    if response.status == "timezone_conflict":
        return "timezone_conflict"
    if response.status == "missing" or not response.bars:
        return "missing"
    if response.status == "partial":
        return "partial"
    return "available"


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


def _bar_metrics(bars: list[MarketBar]) -> dict[str, float | None]:
    total_volume = sum(float(bar.volume) for bar in bars)
    vwap = None if total_volume <= 0 else sum(float(bar.close) * float(bar.volume) for bar in bars) / total_volume
    return {
        "vwap": None if vwap is None else round(vwap, 6),
        "day_high": round(max(float(bar.high) for bar in bars), 6),
        "day_low": round(min(float(bar.low) for bar in bars), 6),
    }


def _volume_context(bars: list[MarketBar], requested_start: str, requested_end: str) -> dict[str, Any]:
    total_volume = sum(float(bar.volume) for bar in bars)
    avg_bar_volume = 0.0 if not bars else total_volume / len(bars)
    return {
        "bar_count": len(bars),
        "requested_start": requested_start,
        "requested_end": requested_end,
        "total_volume": round(total_volume, 6),
        "avg_bar_volume": round(avg_bar_volume, 6),
    }


def _bars_json(bars: list[MarketBar]) -> str:
    return json.dumps([bar.as_dict() for bar in bars], ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _public_archive(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["archive_id"] = payload["id"]
    payload["bar_count"] = int(payload["bar_count"])
    payload["source_fill_count"] = int(payload["source_fill_count"])
    payload["bars"] = json.loads(payload["bars_json"])
    payload["volume_context"] = json.loads(payload["volume_context"])
    for key in ("vwap", "day_high", "day_low"):
        payload[key] = None if payload[key] is None else float(payload[key])
    return payload


def _idempotency_key(
    provider: str,
    symbol: str,
    trade_date: str,
    requested_start: str,
    requested_end: str,
) -> str:
    return f"{provider}:{symbol}:{trade_date}:{requested_start}:{requested_end}"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
