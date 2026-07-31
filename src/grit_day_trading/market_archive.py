from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .futu_provider import FutuMarketDataProvider
from .market_provider import MarketBar, MarketDataProvider, MinuteBarResponse
from .market_quality import archive_preference_key, archive_quality_projection, minute_bar_quality_issue
from .service import list_fills
from .storage import dumps_json, new_id
from .strategy import MOMENTUM_CONTEXT_SYMBOLS, MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY
from .yahoo_provider import YahooFinanceMarketDataProvider


YAHOO_ARCHIVE_PROVIDER = "yahoo"
FUTU_ARCHIVE_PROVIDER = "futu"
ARCHIVE_PROVIDER_CHAIN = (YAHOO_ARCHIVE_PROVIDER, FUTU_ARCHIVE_PROVIDER)
MARKET_MINUTE_ARCHIVE_VERSION = "market_minute_archive_v1"
MINUTE_ARCHIVE_CONTRACT_VERSION = "yahoo_futu_quality_fallback_v2"
REGULAR_SESSION_START = "04:00:00"
REGULAR_SESSION_END = "20:00:00"
SOURCE_FILL_MARKER_TOLERANCE_MINUTES = 1


def archive_yahoo_minutes_for_committed_fills(
    conn: sqlite3.Connection,
    *,
    trade_date: str | None = None,
    force: bool = False,
    provider: MarketDataProvider | None = None,
    fallback_provider: MarketDataProvider | None = None,
) -> dict[str, Any]:
    targets = _archive_targets(conn, trade_date=trade_date)
    items = [
        _archive_market_minutes_with_fallback(
            conn,
            symbol=target["symbol"],
            trade_date=target["trade_date"],
            source_fill_count=target["source_fill_count"],
            force=force,
            primary_provider=provider,
            fallback_provider=fallback_provider,
        )
        for target in targets
    ]
    return _archive_summary(
        {
            "status": "no_targets" if not targets else "completed",
            "provider": YAHOO_ARCHIVE_PROVIDER,
            "archive_version": MARKET_MINUTE_ARCHIVE_VERSION,
            "trade_date": trade_date,
            "target_count": len(targets),
            "stored_count": len(items),
        },
        items,
    )


def archive_yahoo_minutes_for_import_batch(
    conn: sqlite3.Connection,
    *,
    batch_id: str,
    force: bool = False,
    provider: MarketDataProvider | None = None,
    fallback_provider: MarketDataProvider | None = None,
) -> dict[str, Any]:
    targets = _archive_targets(conn, trade_date=None, source_batch_id=batch_id, include_momentum_context=False)
    items = [
        _archive_market_minutes_with_fallback(
            conn,
            symbol=target["symbol"],
            trade_date=target["trade_date"],
            source_fill_count=target["source_fill_count"],
            force=force,
            primary_provider=provider,
            fallback_provider=fallback_provider,
        )
        for target in targets
    ]
    return _archive_summary(
        {
            "status": "no_targets" if not targets else "completed",
            "provider": YAHOO_ARCHIVE_PROVIDER,
            "archive_version": MARKET_MINUTE_ARCHIVE_VERSION,
            "batch_id": batch_id,
            "trade_date": None,
            "target_count": len(targets),
            "stored_count": len(items),
        },
        items,
    )


def archive_yahoo_minutes_for_symbol_window(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    end_date: str,
    window_trading_days: int = 30,
    force: bool = False,
    provider: MarketDataProvider | None = None,
    fallback_provider: MarketDataProvider | None = None,
) -> dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        raise ValueError("archive_symbol_required")
    window = int(window_trading_days)
    if window < 1 or window > 30:
        raise ValueError("archive_window_trading_days_out_of_range")

    trade_dates = _recent_calendar_dates(end_date, window)
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
        _archive_market_minutes_with_fallback(
            conn,
            symbol=target["symbol"],
            trade_date=target["trade_date"],
            source_fill_count=target["source_fill_count"],
            force=force,
            primary_provider=provider,
            fallback_provider=fallback_provider,
        )
        for target in targets
    ]
    selected_items = [item for item in items if item["symbol"] == canonical_symbol]
    return _archive_summary(
        {
            "status": "completed",
            "provider": YAHOO_ARCHIVE_PROVIDER,
            "archive_version": MARKET_MINUTE_ARCHIVE_VERSION,
            "trade_date": end_date,
            "symbol": canonical_symbol,
            "window_trading_days": window,
            "requested_trade_dates": trade_dates,
            "target_count": len(targets),
            "stored_count": len(items),
            "selected_symbol_available_count": sum(
                1 for item in selected_items if item["data_status"] == "available"
            ),
        },
        items,
    )


def archive_yahoo_minutes_for_symbol_group_window(
    conn: sqlite3.Connection,
    *,
    symbols: list[str] | tuple[str, ...],
    end_date: str,
    window_trading_days: int = 1,
    force: bool = False,
    provider: MarketDataProvider | None = None,
    fallback_provider: MarketDataProvider | None = None,
) -> dict[str, Any]:
    target_symbols = _canonical_symbols(symbols)
    if not target_symbols:
        raise ValueError("archive_symbol_required")
    window = int(window_trading_days)
    if window < 1 or window > 30:
        raise ValueError("archive_window_trading_days_out_of_range")

    trade_dates = _recent_calendar_dates(end_date, window)
    all_symbols = list(target_symbols)
    if _has_enabled_momentum_mean_reversion_strategy(conn):
        for context_symbol in MOMENTUM_CONTEXT_SYMBOLS:
            if context_symbol not in all_symbols:
                all_symbols.append(context_symbol)

    targets = [
        {
            "trade_date": target_date,
            "symbol": target_symbol,
            "source_fill_count": _source_fill_count(conn, trade_date=target_date, symbol=target_symbol),
        }
        for target_date in trade_dates
        for target_symbol in all_symbols
    ]
    items = [
        _archive_market_minutes_with_fallback(
            conn,
            symbol=target["symbol"],
            trade_date=target["trade_date"],
            source_fill_count=target["source_fill_count"],
            force=force,
            primary_provider=provider,
            fallback_provider=fallback_provider,
        )
        for target in targets
    ]
    selected_items = [item for item in items if item["symbol"] in target_symbols]
    return _archive_summary(
        {
            "status": "completed",
            "provider": YAHOO_ARCHIVE_PROVIDER,
            "archive_version": MARKET_MINUTE_ARCHIVE_VERSION,
            "trade_date": end_date,
            "symbols": target_symbols,
            "window_trading_days": window,
            "requested_trade_dates": trade_dates,
            "target_count": len(targets),
            "stored_count": len(items),
            "selected_symbol_available_count": sum(
                1 for item in selected_items if item["data_status"] == "available"
            ),
            "per_symbol": {
                symbol: {
                    "target_count": sum(1 for item in selected_items if item["symbol"] == symbol),
                    "available_count": sum(
                        1
                        for item in selected_items
                        if item["symbol"] == symbol and item["data_status"] == "available"
                    ),
                    "non_available_count": sum(
                        1
                        for item in selected_items
                        if item["symbol"] == symbol and item["data_status"] != "available"
                    ),
                }
                for symbol in target_symbols
            },
        },
        items,
    )


def _archive_market_minutes_with_fallback(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    trade_date: str,
    source_fill_count: int,
    force: bool,
    primary_provider: MarketDataProvider | None,
    fallback_provider: MarketDataProvider | None,
) -> dict[str, Any]:
    primary_archive = archive_market_minutes(
        conn,
        symbol=symbol,
        trade_date=trade_date,
        source_fill_count=source_fill_count,
        provider_name=YAHOO_ARCHIVE_PROVIDER,
        force=force,
        provider=primary_provider,
    )
    if primary_archive["data_status"] == "available":
        return primary_archive
    if primary_archive["data_status"] == "missing" and source_fill_count <= 0:
        return primary_archive

    selected_fallback = fallback_provider
    if primary_provider is None and fallback_provider is None:
        selected_fallback = resolve_provider(FUTU_ARCHIVE_PROVIDER)
    if selected_fallback is None:
        return primary_archive

    return archive_market_minutes(
        conn,
        symbol=symbol,
        trade_date=trade_date,
        source_fill_count=source_fill_count,
        provider_name=FUTU_ARCHIVE_PROVIDER,
        force=force,
        provider=selected_fallback,
    )


def _archive_summary(base: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        **base,
        "provider_chain": list(ARCHIVE_PROVIDER_CHAIN),
        "available_count": sum(1 for item in items if item["data_status"] == "available"),
        "non_available_count": sum(1 for item in items if item["data_status"] != "available"),
        "provider_failed_count": sum(1 for item in items if item["data_status"] == "provider_failed"),
        "fallback_attempted_count": sum(1 for item in items if item["provider"] == FUTU_ARCHIVE_PROVIDER),
        "fallback_available_count": sum(
            1
            for item in items
            if item["provider"] == FUTU_ARCHIVE_PROVIDER and item["data_status"] == "available"
        ),
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
    source_fill_times = _source_fill_times(conn, trade_date=trade_date, symbol=canonical_symbol)
    bars_json = _bars_json(response.bars)
    bars_hash = _sha256_text(bars_json)
    payload_hash = _sha256_text(bars_json if response.bars else (response.error_code or response.status))
    data_status = _data_status(response)
    quality_issue = minute_bar_quality_issue(response.bars)
    if data_status in {"available", "partial"} and quality_issue:
        data_status = "partial"
    source_fill_window_covered = _bars_cover_source_fill_times(response.bars, source_fill_times)
    if data_status == "available" and not source_fill_window_covered:
        data_status = "partial"
    metrics = _bar_metrics(response.bars) if response.bars else {"vwap": None, "day_high": None, "day_low": None}
    volume_context = _volume_context(response.bars, requested_start, requested_end)
    failure_reason = _failure_reason(
        response,
        data_status,
        source_fill_window_covered=source_fill_window_covered,
        quality_issue=quality_issue,
    )
    created_at = _now()
    preserve_existing = _should_preserve_existing_archive(
        existing,
        next_status=data_status,
        next_bar_count=len(response.bars),
    )

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
                response.error_code or quality_issue,
                payload_hash,
                created_at,
            ),
        )
        if existing:
            archive_id = existing["id"]
            if preserve_existing:
                conn.execute(
                    "UPDATE market_minute_archives SET source_fill_count = ? WHERE id = ?",
                    (int(source_fill_count), archive_id),
                )
            else:
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
        ORDER BY
            trade_date DESC,
            symbol,
            CASE data_status
                WHEN 'available' THEN 0
                WHEN 'partial' THEN 1
                ELSE 2
            END,
            CASE
                WHEN data_status IN ('available', 'partial') AND provider = 'yahoo' THEN 0
                WHEN data_status IN ('available', 'partial') AND provider = 'futu' THEN 1
                WHEN data_status NOT IN ('available', 'partial') AND provider = 'futu' THEN 0
                WHEN data_status NOT IN ('available', 'partial') AND provider = 'yahoo' THEN 1
                ELSE 2
            END,
            created_at DESC,
            id DESC
        """,
        params,
    ).fetchall()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        item = _public_archive(row)
        grouped.setdefault((item["trade_date"], item["symbol"]), []).append(item)
    return [
        item
        for group in grouped.values()
        for item in sorted(group, key=archive_preference_key)
    ]


def get_market_minute_archive(conn: sqlite3.Connection, archive_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM market_minute_archives WHERE id = ?", (archive_id,)).fetchone()
    if not row:
        raise KeyError("market_minute_archive_not_found")
    return _public_archive(row)


def resolve_provider(provider_name: str) -> MarketDataProvider:
    if provider_name == YAHOO_ARCHIVE_PROVIDER:
        return YahooFinanceMarketDataProvider()
    if provider_name == FUTU_ARCHIVE_PROVIDER:
        return FutuMarketDataProvider(auto_start_opend=True)
    raise ValueError("unsupported_archive_provider")


def _archive_targets(
    conn: sqlite3.Connection,
    *,
    trade_date: str | None,
    source_batch_id: str | None = None,
    include_momentum_context: bool = True,
) -> list[dict[str, Any]]:
    fills = list_fills(conn, date=trade_date)
    counts: dict[tuple[str, str], int] = {}
    for fill in fills:
        if source_batch_id and fill["source_batch_id"] != source_batch_id:
            continue
        key = (str(fill["filled_at"])[:10], str(fill["symbol"]).strip().upper())
        counts[key] = counts.get(key, 0) + 1
    if include_momentum_context and _has_enabled_momentum_mean_reversion_strategy(conn):
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


def _source_fill_times(conn: sqlite3.Connection, *, trade_date: str, symbol: str) -> list[str]:
    canonical_symbol = symbol.strip().upper()
    return [
        str(fill["filled_at"])
        for fill in list_fills(conn, date=trade_date)
        if str(fill["symbol"]).strip().upper() == canonical_symbol
    ]


def _canonical_symbols(symbols: list[str] | tuple[str, ...]) -> list[str]:
    canonical: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        value = str(symbol).strip().upper()
        if not value or value in seen:
            continue
        seen.add(value)
        canonical.append(value)
    return canonical


def _recent_calendar_dates(end_date: str, window_days: int) -> list[str]:
    try:
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("archive_end_date_invalid") from exc

    start = end - timedelta(days=window_days - 1)
    return [(start + timedelta(days=offset)).isoformat() for offset in range(window_days)]


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


def _should_preserve_existing_archive(
    existing: sqlite3.Row | None,
    *,
    next_status: str,
    next_bar_count: int,
) -> bool:
    if existing is None:
        return False
    current_bar_count = int(existing["bar_count"])
    current_status = str(existing["data_status"])
    if current_bar_count > 0 and next_bar_count <= 0:
        return True
    status_rank = {
        "available": 0,
        "partial": 1,
        "missing": 2,
        "timezone_conflict": 3,
        "provider_failed": 4,
    }
    if status_rank.get(next_status, 5) > status_rank.get(current_status, 5):
        return True
    return current_status == next_status == "partial" and next_bar_count < current_bar_count


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


def _failure_reason(
    response: MinuteBarResponse,
    data_status: str,
    *,
    source_fill_window_covered: bool = True,
    quality_issue: str | None = None,
) -> str | None:
    if data_status == "available":
        return None
    if quality_issue:
        return quality_issue
    if response.error_code:
        return response.error_code
    if data_status == "partial" and not source_fill_window_covered:
        return "source_fill_window_not_covered"
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


def _bars_cover_source_fill_times(bars: list[MarketBar], source_fill_times: list[str]) -> bool:
    if not source_fill_times:
        return True
    bar_minutes = [
        minute
        for minute in (_clock_minute(bar.timestamp) for bar in bars)
        if minute is not None
    ]
    if not bar_minutes:
        return False
    for fill_time in source_fill_times:
        target = _clock_minute(fill_time)
        if target is None:
            return False
        if min(abs(minute - target) for minute in bar_minutes) > SOURCE_FILL_MARKER_TOLERANCE_MINUTES:
            return False
    return True


def _clock_minute(value: str) -> int | None:
    if "T" not in value:
        return None
    time_part = value.split("T", 1)[1]
    if len(time_part) < 5 or time_part[2] != ":":
        return None
    try:
        hour = int(time_part[:2])
        minute = int(time_part[3:5])
    except ValueError:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


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
    return archive_quality_projection(payload)


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
