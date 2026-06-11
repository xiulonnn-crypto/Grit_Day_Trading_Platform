from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .parser import FIELD_MAPPER_VERSION, PARSER_VERSION, ParseResult, ParsedRow, parse_stp_txt
from .storage import dumps_json, new_id, row_to_dict, rows_to_dicts

TRADE_GROUP_VERSION = "trade_group_v1"
TRADE_EVALUATION_MODEL_VERSION = "trade_eval_intraday_v1"
TRADE_REVIEW_VERSION = "trade_review_v1"
TRADE_GROUP_ENTRY_ATR_PERIOD = 20
TRADE_REVIEW_CATEGORY_LABELS = {
    "opening_signal": "开仓信号",
    "closing_signal": "平仓信号",
    "misoperation": "误操作",
}
TRADE_REVIEW_REASON_OPTIONS = {
    "opening_signal": [
        {"code": "chased_breakout", "label": "追突破过急"},
        {"code": "weak_confirmation", "label": "确认不足"},
        {"code": "against_context", "label": "逆势入场"},
        {"code": "poor_location", "label": "入场位置差"},
    ],
    "closing_signal": [
        {"code": "stop_too_late", "label": "止损过慢"},
        {"code": "profit_reversed", "label": "盈利回吐"},
        {"code": "exit_signal_ignored", "label": "平仓信号未执行"},
        {"code": "exit_plan_unclear", "label": "平仓计划不清"},
    ],
    "misoperation": [
        {"code": "wrong_side_or_symbol", "label": "方向或标的点错"},
        {"code": "oversized_position", "label": "仓位过大"},
        {"code": "duplicate_order", "label": "重复下单"},
        {"code": "plan_not_followed", "label": "未按计划执行"},
    ],
}


def import_stp_txt(conn: sqlite3.Connection, file_name: str, raw_bytes: bytes) -> dict[str, Any]:
    file_hash = hashlib.sha256(raw_bytes).hexdigest()
    existing = conn.execute("SELECT * FROM import_batches WHERE file_hash = ?", (file_hash,)).fetchone()
    reparse_batch_id: str | None = None
    if existing:
        if _should_reparse_existing_batch(existing):
            reparse_batch_id = existing["id"]
        else:
            summary = get_batch(conn, existing["id"])
            summary["duplicate"] = True
            return summary

    parse_result = parse_stp_txt(raw_bytes)
    batch_id = reparse_batch_id or new_id("batch")
    if parse_result.file_error:
        if reparse_batch_id:
            conn.execute(
                """
                UPDATE import_batches
                SET file_name = ?, uploaded_at = ?, parser_version = ?, field_mapper_version = ?,
                    status = ?, status_reason = ?, row_count = 0, accepted_rows = 0, quarantined_rows = 0
                WHERE id = ?
                """,
                (
                    Path(file_name).name or "stp.txt",
                    _now(),
                    parse_result.parser_version,
                    parse_result.field_mapper_version,
                    "failed",
                    parse_result.file_error,
                    batch_id,
                ),
            )
            conn.commit()
        else:
            conn.execute(
                """
                INSERT INTO import_batches (
                    id, file_name, file_hash, uploaded_at, parser_version, field_mapper_version,
                    status, status_reason, row_count, accepted_rows, quarantined_rows
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0)
                """,
                (
                    batch_id,
                    Path(file_name).name or "stp.txt",
                    file_hash,
                    _now(),
                    parse_result.parser_version,
                    parse_result.field_mapper_version,
                    "failed",
                    parse_result.file_error,
                ),
            )
            conn.commit()
        return get_batch(conn, batch_id)

    accepted = sum(1 for row in parse_result.rows if row.row_status == "accepted")
    quarantined = sum(1 for row in parse_result.rows if row.row_status == "quarantine")
    status = "committed" if accepted > 0 else "failed"
    status_reason = "contains_quarantine_rows" if accepted > 0 and quarantined else ("no_valid_rows" if accepted == 0 else None)

    with conn:
        if reparse_batch_id:
            conn.execute("DELETE FROM fills WHERE source_batch_id = ?", (batch_id,))
            conn.execute("DELETE FROM orders WHERE source_batch_id = ?", (batch_id,))
            conn.execute("DELETE FROM quarantine_rows WHERE batch_id = ?", (batch_id,))
            conn.execute("DELETE FROM import_rows WHERE batch_id = ?", (batch_id,))
            conn.execute(
                """
                UPDATE import_batches
                SET file_name = ?, uploaded_at = ?, parser_version = ?, field_mapper_version = ?,
                    status = ?, status_reason = ?, row_count = ?, accepted_rows = ?, quarantined_rows = ?
                WHERE id = ?
                """,
                (
                    Path(file_name).name or "stp.txt",
                    _now(),
                    parse_result.parser_version,
                    parse_result.field_mapper_version,
                    status,
                    status_reason,
                    len(parse_result.rows),
                    accepted,
                    quarantined,
                    batch_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO import_batches (
                    id, file_name, file_hash, uploaded_at, parser_version, field_mapper_version,
                    status, status_reason, row_count, accepted_rows, quarantined_rows
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    Path(file_name).name or "stp.txt",
                    file_hash,
                    _now(),
                    parse_result.parser_version,
                    parse_result.field_mapper_version,
                    status,
                    status_reason,
                    len(parse_result.rows),
                    accepted,
                    quarantined,
                ),
            )
        for row in parse_result.rows:
            _insert_import_row(conn, batch_id, parse_result, row)

    return get_batch(conn, batch_id)


def get_batch(conn: sqlite3.Connection, batch_id: str) -> dict[str, Any]:
    batch = row_to_dict(conn.execute("SELECT * FROM import_batches WHERE id = ?", (batch_id,)).fetchone())
    if not batch:
        raise KeyError(batch_id)
    return _public_batch(batch)


def list_batches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM import_batches ORDER BY uploaded_at DESC, id DESC").fetchall()
    return [_public_batch(row_to_dict(row)) for row in rows]


def list_quarantine(conn: sqlite3.Connection, batch_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, batch_id, import_row_id, raw_line_number, raw_text, failed_field,
               reason_code, reason, repair_hint, review_status
        FROM quarantine_rows
        WHERE batch_id = ?
        ORDER BY raw_line_number
        """,
        (batch_id,),
    ).fetchall()
    return [_public_quarantine_row(row) for row in rows_to_dicts(rows)]


def list_fills(
    conn: sqlite3.Connection,
    *,
    date: str | None = None,
    account: str | None = None,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if date:
        clauses.append("substr(f.filled_at, 1, 10) = ?")
        params.append(date)
    if account:
        clauses.append("f.account_canonical = ?")
        params.append(account.strip().upper())
    if symbol:
        clauses.append("f.symbol = ?")
        params.append(symbol.strip().upper())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT f.*, r.raw_line_number, b.parser_version, b.field_mapper_version,
               b.uploaded_at AS _batch_uploaded_at
        FROM fills f
        JOIN import_rows r ON r.id = f.source_import_row_id
        JOIN import_batches b ON b.id = f.source_batch_id
        {where}
        ORDER BY filled_at, id
        """,
        params,
    ).fetchall()
    return [_public_fill(row) for row in _dedupe_fill_read_model(rows_to_dicts(rows))]


def daily_summary(conn: sqlite3.Connection, date: str) -> dict[str, Any]:
    return review_summary(conn, date=date)


def review_summary(
    conn: sqlite3.Connection,
    *,
    date: str | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    canonical_symbol = symbol.strip().upper() if symbol else None
    all_fills = list_fills(conn, symbol=canonical_symbol)
    fills = _filter_summary_fills(all_fills, date=date, symbol=canonical_symbol)
    groups = _filter_summary_groups(
        _light_trade_groups_from_fills(all_fills),
        date=date,
        symbol=canonical_symbol,
    )
    return _review_summary_from_models(conn, fills, groups, date=date, symbol=canonical_symbol)


def _review_summary_from_models(
    conn: sqlite3.Connection,
    fills: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    *,
    date: str | None,
    symbol: str | None,
) -> dict[str, Any]:
    closed_groups = [group for group in groups if group["status"] == "closed"]
    open_groups = [group for group in groups if group["status"] == "open"]
    realized = [float(group["pnl"]) for group in closed_groups if group["pnl"] is not None]
    traded_quantity = sum(float(group["total_quantity"]) for group in closed_groups)
    wins = [value for value in realized if value > 0]
    losses = [value for value in realized if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    win_rate = (len(wins) / len(realized)) if realized else 0.0
    loss_rate = (len(losses) / len(realized)) if realized else 0.0
    average_profit = (gross_profit / len(wins)) if wins else 0.0
    average_loss = (gross_loss / len(losses)) if losses else 0.0
    profit_factor = None if gross_loss == 0 else gross_profit / gross_loss
    expected_value = None if not realized else win_rate * average_profit - loss_rate * average_loss
    pnl = sum(realized)
    net_profit_per_share = None if traded_quantity <= 0 else pnl / traded_quantity
    max_single_day_drawdown = _max_position_drawdown(conn, closed_groups)
    batch_ids = sorted({fill["source_batch_id"] for fill in fills})
    quarantine_count = 0
    if batch_ids:
        placeholders = ",".join("?" for _ in batch_ids)
        quarantine_count = conn.execute(
            f"SELECT COUNT(*) AS count FROM quarantine_rows WHERE batch_id IN ({placeholders})",
            batch_ids,
        ).fetchone()["count"]
    elif date is None and symbol is None:
        quarantine_count = conn.execute("SELECT COUNT(*) AS count FROM quarantine_rows").fetchone()["count"]
    return {
        "date": date,
        "symbol": symbol,
        "fill_count": len(fills),
        "trade_group_count": len(closed_groups),
        "open_trade_group_count": len(open_groups),
        "traded_quantity": _round_quantity(traded_quantity),
        "pnl": round(pnl, 6),
        "win_rate": round(win_rate, 6),
        "profit_factor": None if profit_factor is None else round(profit_factor, 6),
        "expected_value_per_trade": None if expected_value is None else round(expected_value, 6),
        "net_profit_per_share": None if net_profit_per_share is None else round(net_profit_per_share, 6),
        "max_single_day_drawdown": round(max_single_day_drawdown, 6),
        "quarantine_row_count": quarantine_count,
        "source": "committed_fills_only",
    }


def review_summary_groups(
    conn: sqlite3.Connection,
    *,
    group_by: str,
    date: str | None = None,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    canonical_symbol = symbol.strip().upper() if symbol else None
    all_fills = list_fills(conn, symbol=canonical_symbol)
    all_groups = _light_trade_groups_from_fills(all_fills)
    if group_by == "date":
        group_keys = sorted(
            {str(fill["filled_at"])[:10] for fill in all_fills},
            reverse=True,
        )
        return [
            _summary_group_payload(
                "date",
                key,
                _review_summary_from_models(
                    conn,
                    _filter_summary_fills(all_fills, date=key, symbol=canonical_symbol),
                    _filter_summary_groups(all_groups, date=key, symbol=canonical_symbol),
                    date=key,
                    symbol=canonical_symbol,
                ),
            )
            for key in group_keys
        ]
    if group_by == "symbol":
        group_keys = sorted({fill["symbol"] for fill in _filter_summary_fills(all_fills, date=date, symbol=canonical_symbol)})
        return [
            _summary_group_payload(
                "symbol",
                key,
                _review_summary_from_models(
                    conn,
                    _filter_summary_fills(all_fills, date=date, symbol=key),
                    _filter_summary_groups(all_groups, date=date, symbol=key),
                    date=date,
                    symbol=key,
                ),
            )
            for key in group_keys
        ]
    raise ValueError("unsupported_summary_group")


def list_trade_groups(
    conn: sqlite3.Connection,
    *,
    date: str | None = None,
    account: str | None = None,
    symbol: str | None = None,
    include_details: bool = True,
) -> list[dict[str, Any]]:
    groups = _light_trade_groups(conn, account=account, symbol=symbol)
    if date:
        groups = [group for group in groups if _group_belongs_to_date(group, date)]
    return [_public_trade_group(conn, group, include_details=include_details) for group in groups]


def save_trade_group_review(
    conn: sqlite3.Connection,
    trade_group_id: str,
    *,
    reason_category: str,
    reason_code: str,
    note: str = "",
) -> dict[str, Any]:
    group = _find_trade_group(conn, trade_group_id)
    if group["status"] != "closed" or group["pnl"] is None:
        raise ValueError("trade_review_requires_closed_loss")
    if float(group["pnl"]) >= 0:
        raise ValueError("trade_review_requires_loss")
    reason_label = _trade_review_reason_label(reason_category, reason_code)
    now = _now()
    idempotency_key = _trade_review_idempotency_key(trade_group_id)
    cleaned_note = note.strip()
    existing = conn.execute("SELECT id, created_at FROM trade_reviews WHERE trade_group_id = ?", (trade_group_id,)).fetchone()
    review_id = existing["id"] if existing else new_id("review")
    created_at = existing["created_at"] if existing else now
    payload = (
        review_id,
        trade_group_id,
        group["account_canonical"],
        group["symbol"],
        str(group["closed_at"])[:10],
        float(group["pnl"]),
        reason_category,
        reason_code,
        reason_label,
        cleaned_note,
        json.dumps(group["parser_versions"], ensure_ascii=False, sort_keys=True),
        json.dumps(group["field_mapper_versions"], ensure_ascii=False, sort_keys=True),
        json.dumps(group["source_batch_ids"], ensure_ascii=False, sort_keys=True),
        json.dumps(group["raw_line_numbers"], ensure_ascii=False, sort_keys=True),
        idempotency_key,
        created_at,
        now,
    )
    with conn:
        if existing:
            conn.execute(
                """
                UPDATE trade_reviews
                SET account_canonical = ?, symbol = ?, trade_date = ?, pnl = ?,
                    reason_category = ?, reason_code = ?, reason_label = ?, note = ?,
                    parser_versions_json = ?, field_mapper_versions_json = ?,
                    source_batch_ids_json = ?, raw_line_numbers_json = ?,
                    idempotency_key = ?, updated_at = ?
                WHERE trade_group_id = ?
                """,
                (
                    payload[2],
                    payload[3],
                    payload[4],
                    payload[5],
                    payload[6],
                    payload[7],
                    payload[8],
                    payload[9],
                    payload[10],
                    payload[11],
                    payload[12],
                    payload[13],
                    payload[14],
                    payload[16],
                    trade_group_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO trade_reviews (
                    id, trade_group_id, account_canonical, symbol, trade_date, pnl,
                    reason_category, reason_code, reason_label, note,
                    parser_versions_json, field_mapper_versions_json,
                    source_batch_ids_json, raw_line_numbers_json,
                    idempotency_key, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
    review = _trade_group_review(conn, trade_group_id)
    if review is None:
        raise KeyError(trade_group_id)
    return review


def _light_trade_groups(
    conn: sqlite3.Connection,
    *,
    account: str | None = None,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    return _light_trade_groups_from_fills(_fills_with_internal_signatures(conn, account=account, symbol=symbol))


def _find_trade_group(conn: sqlite3.Connection, trade_group_id: str) -> dict[str, Any]:
    for group in _light_trade_groups(conn):
        if group["trade_group_id"] == trade_group_id:
            return group
    raise KeyError(trade_group_id)


def _light_trade_groups_from_fills(fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signed_fills = [
        {
            **fill,
            "_idempotency_signature": hashlib.sha256(str(fill["idempotency_key"]).encode("utf-8")).hexdigest(),
        }
        for fill in fills
    ]
    return _build_trade_groups(signed_fills)


def _filter_summary_fills(
    fills: list[dict[str, Any]],
    *,
    date: str | None = None,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    canonical_symbol = symbol.strip().upper() if symbol else None
    return [
        fill
        for fill in fills
        if (date is None or str(fill["filled_at"])[:10] == date)
        and (canonical_symbol is None or fill["symbol"] == canonical_symbol)
    ]


def _filter_summary_groups(
    groups: list[dict[str, Any]],
    *,
    date: str | None = None,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    canonical_symbol = symbol.strip().upper() if symbol else None
    return [
        group
        for group in groups
        if (date is None or _group_belongs_to_date(group, date))
        and (canonical_symbol is None or group["symbol"] == canonical_symbol)
    ]


def _should_reparse_existing_batch(existing: sqlite3.Row) -> bool:
    version_drifted = existing["parser_version"] != PARSER_VERSION or existing["field_mapper_version"] != FIELD_MAPPER_VERSION
    if not version_drifted:
        return False
    if existing["status"] == "failed" and int(existing["row_count"]) == 0:
        return True
    return existing["status"] == "committed"


def _round_quantity(value: float) -> int | float:
    return int(value) if value.is_integer() else round(value, 6)


def _summary_group_payload(group_by: str, group_key: str, summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "group_by": group_by,
        "group_key": group_key,
        "group_label": group_key,
        **summary,
    }


def _max_position_drawdown(conn: sqlite3.Connection, closed_groups: list[dict[str, Any]]) -> float:
    drawdowns: list[float] = []
    archive_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    for group in closed_groups:
        position_drawdown = group.get("position_drawdown") or _trade_group_position_drawdown(conn, group, archive_cache=archive_cache)
        if position_drawdown.get("status") != "available":
            continue
        max_drawdown = position_drawdown.get("max_drawdown")
        if max_drawdown is not None:
            drawdowns.append(float(max_drawdown))
    return max(drawdowns) if drawdowns else 0.0


def _fills_with_internal_signatures(
    conn: sqlite3.Connection,
    *,
    account: str | None = None,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    fills = list_fills(conn, account=account, symbol=symbol)
    if not fills:
        return []
    fill_ids = [fill["fill_id"] for fill in fills]
    placeholders = ",".join("?" for _ in fill_ids)
    rows = conn.execute(
        f"SELECT id, idempotency_key FROM fills WHERE id IN ({placeholders})",
        fill_ids,
    ).fetchall()
    signatures = {row["id"]: hashlib.sha256(row["idempotency_key"].encode("utf-8")).hexdigest() for row in rows}
    return [{**fill, "_idempotency_signature": signatures.get(fill["fill_id"], fill["fill_id"])} for fill in fills]


def _build_trade_groups(fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    states: dict[tuple[str, str], dict[str, Any]] = {}
    groups: list[dict[str, Any]] = []
    ordered_fills = sorted(
        fills,
        key=lambda item: (item["account_canonical"], item["symbol"], item["filled_at"], item["fill_id"]),
    )
    for fill in ordered_fills:
        key = (fill["account_canonical"], fill["symbol"])
        side_sign = 1.0 if fill["side"] == "BUY" else -1.0
        remaining_quantity = float(fill["quantity"])
        while remaining_quantity > 1e-9:
            state = states.get(key)
            if not state or _is_flat(float(state["position"])):
                state = _new_trade_group_state(fill, side_sign)
                states[key] = state
                _append_trade_group_fill(state, fill, remaining_quantity, side_sign)
                remaining_quantity = 0.0
                continue

            position = float(state["position"])
            if position * side_sign > 0:
                _append_trade_group_fill(state, fill, remaining_quantity, side_sign)
                remaining_quantity = 0.0
                continue

            close_quantity = min(abs(position), remaining_quantity)
            _append_trade_group_fill(state, fill, close_quantity, side_sign)
            remaining_quantity -= close_quantity
            if _is_flat(float(state["position"])):
                groups.append(_finalize_trade_group(state, status="closed"))
                states.pop(key, None)

    open_groups = [_finalize_trade_group(state, status="open") for state in states.values() if not _is_flat(float(state["position"]))]
    return sorted([*groups, *open_groups], key=lambda item: (item["opened_at"], item["trade_group_id"]))


def _new_trade_group_state(fill: dict[str, Any], side_sign: float) -> dict[str, Any]:
    return {
        "account_raw": fill["account_raw"],
        "account_canonical": fill["account_canonical"],
        "symbol": fill["symbol"],
        "direction": "LONG" if side_sign > 0 else "SHORT",
        "position": 0.0,
        "cash": 0.0,
        "fills": [],
    }


def _append_trade_group_fill(state: dict[str, Any], fill: dict[str, Any], quantity: float, side_sign: float) -> None:
    rounded_quantity = float(_round_quantity(quantity))
    price = float(fill["price"])
    state["fills"].append(
        {
            "id": fill["id"],
            "fill_id": fill["fill_id"],
            "account_raw": fill["account_raw"],
            "account_canonical": fill["account_canonical"],
            "symbol": fill["symbol"],
            "side": fill["side"],
            "order_id": fill["order_id"],
            "execution_id": fill["execution_id"],
            "filled_at": fill["filled_at"],
            "quantity": rounded_quantity,
            "price": price,
            "source_batch_id": fill["source_batch_id"],
            "source_import_row_id": fill["source_import_row_id"],
            "raw_line_number": fill["raw_line_number"],
            "parser_version": fill["parser_version"],
            "field_mapper_version": fill["field_mapper_version"],
            "uses_fallback_idempotency_key": fill["uses_fallback_idempotency_key"],
            "_idempotency_signature": fill["_idempotency_signature"],
        }
    )
    state["position"] = float(state["position"]) + side_sign * quantity
    state["cash"] = float(state["cash"]) + _cash_delta(side_sign, quantity, price)


def _finalize_trade_group(state: dict[str, Any], *, status: str) -> dict[str, Any]:
    fills = state["fills"]
    direction = state["direction"]
    entry_side = "BUY" if direction == "LONG" else "SELL"
    exit_side = "SELL" if direction == "LONG" else "BUY"
    entry_fills = [fill for fill in fills if fill["side"] == entry_side]
    exit_fills = [fill for fill in fills if fill["side"] == exit_side]
    opened_at = fills[0]["filled_at"]
    closed_at = fills[-1]["filled_at"] if status == "closed" else None
    entry_quantity = sum(float(fill["quantity"]) for fill in entry_fills)
    exit_quantity = sum(float(fill["quantity"]) for fill in exit_fills)
    total_quantity = min(entry_quantity, exit_quantity) if status == "closed" else abs(float(state["position"]))
    group = {
        "account_raw": state["account_raw"],
        "account_canonical": state["account_canonical"],
        "symbol": state["symbol"],
        "direction": direction,
        "status": status,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "holding_minutes": None if closed_at is None else _holding_minutes(opened_at, closed_at),
        "fill_count": len(fills),
        "total_quantity": _round_quantity(total_quantity),
        "entry_quantity": _round_quantity(entry_quantity),
        "exit_quantity": _round_quantity(exit_quantity),
        "avg_entry_price": _weighted_average_price(entry_fills),
        "avg_exit_price": _weighted_average_price(exit_fills),
        "pnl": round(float(state["cash"]), 6) if status == "closed" else None,
        "source": "committed_fills_only",
        "parser_versions": sorted({fill["parser_version"] for fill in fills}),
        "field_mapper_versions": sorted({fill["field_mapper_version"] for fill in fills}),
        "source_batch_ids": sorted({fill["source_batch_id"] for fill in fills}),
        "raw_line_numbers": [int(fill["raw_line_number"]) for fill in fills],
        "fills": fills,
    }
    group["trade_group_id"] = _trade_group_id(group)
    group["id"] = group["trade_group_id"]
    return group


def _public_trade_group(conn: sqlite3.Connection, group: dict[str, Any], *, include_details: bool = True) -> dict[str, Any]:
    public_group = {**group, "fills": [_public_trade_group_fill(fill) for fill in group["fills"]]}
    public_group["position_drawdown"] = _trade_group_position_drawdown(conn, public_group)
    public_group["evaluation"] = _evaluate_trade_group(conn, public_group)
    public_group["details_loaded"] = include_details
    public_group["review"] = _trade_group_review(conn, public_group["trade_group_id"])
    if not include_details:
        public_group["fills"] = []
        public_group["evaluation"] = {
            **public_group["evaluation"],
            "factors": [],
            "strengths": [],
            "risks": [],
        }
    return public_group


def _public_trade_group_fill(fill: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fill.items() if not key.startswith("_")}


def _trade_group_id(group: dict[str, Any]) -> str:
    signature_parts = [
        f"{fill['_idempotency_signature']}:{fill['side']}:{_numeric_signature(fill['quantity'])}"
        for fill in group["fills"]
    ]
    source = "|".join(
        [
            TRADE_GROUP_VERSION,
            group["account_canonical"],
            group["symbol"],
            group["direction"],
            group["opened_at"],
            group["closed_at"] or "open",
            *signature_parts,
        ]
    )
    return f"tg_{hashlib.sha256(source.encode('utf-8')).hexdigest()}"


def _trade_group_review(conn: sqlite3.Connection, trade_group_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM trade_reviews WHERE trade_group_id = ?", (trade_group_id,)).fetchone()
    return _public_trade_review(row_to_dict(row)) if row else None


def _public_trade_review(review: dict[str, Any] | None) -> dict[str, Any] | None:
    if not review:
        return None
    category = review["reason_category"]
    return {
        "id": review["id"],
        "trade_group_id": review["trade_group_id"],
        "account_canonical": review["account_canonical"],
        "symbol": review["symbol"],
        "trade_date": review["trade_date"],
        "pnl": None if review["pnl"] is None else float(review["pnl"]),
        "reason_category": category,
        "reason_category_label": TRADE_REVIEW_CATEGORY_LABELS[category],
        "reason_code": review["reason_code"],
        "reason_label": review["reason_label"],
        "note": review["note"],
        "parser_versions": json.loads(review["parser_versions_json"]),
        "field_mapper_versions": json.loads(review["field_mapper_versions_json"]),
        "source_batch_ids": json.loads(review["source_batch_ids_json"]),
        "raw_line_numbers": json.loads(review["raw_line_numbers_json"]),
        "source": review["source"],
        "artifact_source": review["artifact_source"],
        "idempotency_key": review["idempotency_key"],
        "created_at": review["created_at"],
        "updated_at": review["updated_at"],
    }


def _trade_review_reason_label(reason_category: str, reason_code: str) -> str:
    if reason_category not in TRADE_REVIEW_REASON_OPTIONS:
        raise ValueError("unsupported_trade_review_category")
    for option in TRADE_REVIEW_REASON_OPTIONS[reason_category]:
        if option["code"] == reason_code:
            return option["label"]
    raise ValueError("unsupported_trade_review_reason")


def _trade_review_idempotency_key(trade_group_id: str) -> str:
    source = f"{TRADE_REVIEW_VERSION}:{trade_group_id}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _weighted_average_price(fills: list[dict[str, Any]]) -> float | None:
    quantity = sum(float(fill["quantity"]) for fill in fills)
    if quantity <= 0:
        return None
    return round(sum(float(fill["quantity"]) * float(fill["price"]) for fill in fills) / quantity, 6)


def _holding_minutes(opened_at: str, closed_at: str) -> float:
    opened = _parse_trade_time(opened_at)
    closed = _parse_trade_time(closed_at)
    return round((closed - opened).total_seconds() / 60, 2)


def _parse_trade_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _group_belongs_to_date(group: dict[str, Any], date: str) -> bool:
    if group["status"] == "closed":
        return str(group["closed_at"])[:10] == date
    return any(str(fill["filled_at"])[:10] == date for fill in group["fills"])


def _evaluate_trade_group(conn: sqlite3.Connection, group: dict[str, Any]) -> dict[str, Any]:
    base = {
        "model_version": TRADE_EVALUATION_MODEL_VERSION,
        "evaluation_status": "not_applicable_open_trade" if group["status"] != "closed" else "insufficient_market_data",
        "score": None,
        "grade": None,
        "summary": "未清仓交易不生成系统评价。" if group["status"] != "closed" else "缺少可用分钟线，暂不生成系统评价。",
        "strengths": [],
        "risks": [],
        "factors": [],
    }
    if group["status"] != "closed":
        return base

    archive = _find_trade_group_archive(conn, group)
    if not archive or archive["data_status"] in {"provider_failed", "missing", "timezone_conflict"}:
        return base
    bars = json.loads(archive["bars_json"])
    if not bars:
        return base

    factors = _trade_evaluation_factors(group, bars, archive)
    score = round(sum(float(factor["score"]) for factor in factors), 2)
    grade = _grade_trade_score(score)
    strengths = [factor["label"] for factor in factors if float(factor["score"]) >= float(factor["max_score"]) * 0.7]
    risks = [factor["label"] for factor in factors if float(factor["score"]) < float(factor["max_score"]) * 0.4]
    return {
        **base,
        "evaluation_status": "available",
        "score": score,
        "grade": grade,
        "summary": _trade_evaluation_summary(group, grade),
        "strengths": strengths[:3],
        "risks": risks[:3],
        "factors": factors,
    }


def _find_trade_group_archive(
    conn: sqlite3.Connection,
    group: dict[str, Any],
    archive_cache: dict[tuple[str, str], dict[str, Any] | None] | None = None,
) -> dict[str, Any] | None:
    trade_date = str(group["opened_at"])[:10]
    cache_key = (group["symbol"], trade_date)
    if archive_cache is not None and cache_key in archive_cache:
        return archive_cache[cache_key]
    row = conn.execute(
        """
        SELECT * FROM market_minute_archives
        WHERE provider = 'yahoo' AND symbol = ? AND trade_date = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (group["symbol"], trade_date),
    ).fetchone()
    archive = row_to_dict(row)
    if archive_cache is not None:
        archive_cache[cache_key] = archive
    return archive


def _trade_group_position_drawdown(
    conn: sqlite3.Connection,
    group: dict[str, Any],
    *,
    archive_cache: dict[tuple[str, str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    base = {
        "status": "not_applicable_open_trade" if group["status"] != "closed" else "insufficient_market_data",
        "max_drawdown": None,
        "max_drawdown_per_share": None,
        "source": None,
        "source_archive_id": None,
        "bars_hash": None,
        "bar_count": 0,
        "window_start": group["opened_at"],
        "window_end": group["closed_at"],
        "window_high": None,
        "window_low": None,
        "worst_price": None,
        "price_basis": None,
        "entry_atr_period": TRADE_GROUP_ENTRY_ATR_PERIOD,
        "entry_atr": None,
        "entry_bar_range": None,
        "entry_atr_multiple": None,
        "entry_atr_regime": "missing",
        "entry_atr_source_archive_id": None,
        "entry_atr_bars_hash": None,
        "entry_atr_bar_timestamp": None,
        "entry_atr_failure_reason": None,
    }

    archive = _find_trade_group_archive(conn, group, archive_cache)
    if not archive or archive["data_status"] in {"provider_failed", "missing", "timezone_conflict"}:
        return {**base, "entry_atr_failure_reason": "missing_market_data"}
    bars = json.loads(archive["bars_json"])
    if not bars:
        return {**base, "entry_atr_failure_reason": "missing_market_data"}

    base = {**base, **_trade_group_entry_atr_payload(bars, str(group["opened_at"]), archive)}
    if group["status"] != "closed":
        return base

    scoped = _bars_for_trade_window(bars, str(group["opened_at"]), str(group["closed_at"]))
    if not scoped:
        return base

    window_high = max(float(bar["high"]) for bar in scoped)
    window_low = min(float(bar["low"]) for bar in scoped)
    avg_entry = float(group["avg_entry_price"] or 0)
    quantity = float(group["total_quantity"] or 0)
    if avg_entry <= 0 or quantity <= 0:
        return base

    if group["direction"] == "SHORT":
        drawdown_per_share = max(window_high - avg_entry, 0.0)
        worst_price = window_high
    else:
        drawdown_per_share = max(avg_entry - window_low, 0.0)
        worst_price = window_low

    return {
        **base,
        "status": "available",
        "max_drawdown": round(drawdown_per_share * quantity, 6),
        "max_drawdown_per_share": round(drawdown_per_share, 6),
        "source": "market_minute_archives",
        "source_archive_id": archive["id"],
        "bars_hash": archive["bars_hash"],
        "bar_count": len(scoped),
        "window_high": round(window_high, 6),
        "window_low": round(window_low, 6),
        "worst_price": round(worst_price, 6),
        "price_basis": "minute_high_low",
    }


def _trade_group_entry_atr_payload(
    bars: list[dict[str, Any]],
    opened_at: str,
    archive: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "entry_atr_source_archive_id": archive["id"],
        "entry_atr_bars_hash": archive["bars_hash"],
        "entry_atr_failure_reason": None,
    }
    opened_minute = _clock_minute(opened_at)
    ordered_bars = sorted(
        [(minute, bar) for bar in bars if (minute := _clock_minute(str(bar.get("timestamp", "")))) is not None],
        key=lambda item: item[0],
    )
    if opened_minute is None or not ordered_bars:
        return {**payload, "entry_atr_failure_reason": "entry_bar_not_found"}

    entry_index = next((index for index, (minute, _bar) in enumerate(ordered_bars) if minute >= opened_minute), None)
    if entry_index is None:
        return {**payload, "entry_atr_failure_reason": "entry_bar_not_found"}
    if entry_index < TRADE_GROUP_ENTRY_ATR_PERIOD:
        return {**payload, "entry_atr_failure_reason": "insufficient_atr_history"}

    history = ordered_bars[entry_index - TRADE_GROUP_ENTRY_ATR_PERIOD : entry_index]
    true_ranges: list[float] = []
    previous_bar: dict[str, Any] | None = None
    if entry_index - TRADE_GROUP_ENTRY_ATR_PERIOD > 0:
        previous_bar = ordered_bars[entry_index - TRADE_GROUP_ENTRY_ATR_PERIOD - 1][1]
    for _minute, bar in history:
        true_range = _bar_true_range(bar, previous_bar)
        if true_range is None:
            return {**payload, "entry_atr_failure_reason": "invalid_atr"}
        true_ranges.append(true_range)
        previous_bar = bar

    entry_bar = ordered_bars[entry_index][1]
    entry_bar_range = _bar_range(entry_bar)
    if entry_bar_range is None:
        return {**payload, "entry_atr_failure_reason": "invalid_atr"}
    entry_atr = sum(true_ranges) / len(true_ranges)
    if entry_atr <= 0:
        return {**payload, "entry_atr_failure_reason": "invalid_atr"}

    entry_atr_multiple = entry_bar_range / entry_atr
    return {
        **payload,
        "entry_atr": round(entry_atr, 6),
        "entry_bar_range": round(entry_bar_range, 6),
        "entry_atr_multiple": round(entry_atr_multiple, 6),
        "entry_atr_regime": _entry_atr_regime(entry_atr_multiple),
        "entry_atr_bar_timestamp": entry_bar.get("timestamp"),
    }


def _entry_atr_regime(entry_atr_multiple: float) -> str:
    if entry_atr_multiple > 3.0:
        return "extreme"
    if entry_atr_multiple >= 1.5:
        return "high"
    if entry_atr_multiple >= 0.5:
        return "normal"
    return "low"


def _bar_true_range(bar: dict[str, Any], previous_bar: dict[str, Any] | None) -> float | None:
    high = _bar_number(bar, "high")
    low = _bar_number(bar, "low")
    if high is None or low is None:
        return None
    ranges = [max(high - low, 0.0)]
    previous_close = None if previous_bar is None else _bar_number(previous_bar, "close")
    if previous_close is not None:
        ranges.extend([abs(high - previous_close), abs(low - previous_close)])
    return max(ranges)


def _bar_range(bar: dict[str, Any]) -> float | None:
    high = _bar_number(bar, "high")
    low = _bar_number(bar, "low")
    if high is None or low is None:
        return None
    return max(high - low, 0.0)


def _bar_number(bar: dict[str, Any], key: str) -> float | None:
    try:
        return float(bar[key])
    except (KeyError, TypeError, ValueError):
        return None


def _trade_evaluation_factors(
    group: dict[str, Any],
    bars: list[dict[str, Any]],
    archive: dict[str, Any],
) -> list[dict[str, Any]]:
    direction_sign = 1.0 if group["direction"] == "LONG" else -1.0
    avg_entry = float(group["avg_entry_price"] or 0)
    avg_exit = float(group["avg_exit_price"] or 0)
    pnl = float(group["pnl"] or 0)
    vwap = None if archive["vwap"] is None else float(archive["vwap"])
    scoped = _bars_for_trade_window(bars, str(group["opened_at"]), str(group["closed_at"]))
    scoped = scoped or bars
    first_open = float(scoped[0]["open"])
    last_close = float(scoped[-1]["close"])
    high = max(float(bar["high"]) for bar in scoped)
    low = min(float(bar["low"]) for bar in scoped)
    total_volume = sum(float(bar["volume"]) for bar in scoped)
    avg_volume = float(json.loads(archive["volume_context"]).get("avg_bar_volume", 0) or 0)
    vwap_edge = 0.0 if vwap is None else direction_sign * (vwap - avg_entry) + direction_sign * (avg_exit - vwap)
    trend_edge = direction_sign * (last_close - first_open)
    range_size = max(high - low, 0.01)
    mfe = max(high - avg_entry, 0.0)
    mae = max(avg_entry - low, 0.0)
    if group["direction"] == "SHORT":
        mfe = max(avg_entry - low, 0.0)
        mae = max(high - avg_entry, 0.0)
    exit_efficiency = (avg_exit - low) / range_size if group["direction"] == "LONG" else (high - avg_exit) / range_size
    relative_volume = 1.0 if avg_volume <= 0 else (total_volume / max(len(scoped), 1)) / avg_volume

    return [
        _factor("vwap_execution", "VWAP 执行质量", _bounded_score(vwap_edge / max(avg_entry, 0.01), 0.002, 20), 20, "进出场相对 VWAP 的综合质量。"),
        _factor("momentum_alignment", "趋势配合", _bounded_score(trend_edge / max(first_open, 0.01), 0.004, 20), 20, "持仓窗口内价格方向是否配合交易方向。"),
        _factor("volume_confirmation", "成交量确认", min(15.0, max(0.0, relative_volume * 7.5)), 15, "持仓窗口量能相对日内平均量能。"),
        _factor("mfe_mae", "MFE/MAE 风险回报", min(20.0, (mfe / max(mae, 0.01)) * 8.0), 20, "最大有利波动与最大不利波动的比例。"),
        _factor("exit_efficiency", "清仓效率", min(15.0, max(0.0, exit_efficiency * 15.0)), 15, "清仓价在持仓高低区间中的位置。"),
        _factor("pnl_result", "PnL 结果", 10.0 if pnl > 0 else (5.0 if abs(pnl) < 1e-9 else 0.0), 10, "本次交易已实现盈亏。"),
    ]


def _bars_for_trade_window(bars: list[dict[str, Any]], opened_at: str, closed_at: str) -> list[dict[str, Any]]:
    opened_minute = _clock_minute(opened_at)
    closed_minute = _clock_minute(closed_at)
    if opened_minute is None or closed_minute is None:
        return bars
    return [
        bar
        for bar in bars
        if (minute := _clock_minute(str(bar["timestamp"]))) is not None and opened_minute <= minute <= closed_minute
    ]


def _clock_minute(value: str) -> int | None:
    if "T" not in value:
        return None
    clock = value.split("T", 1)[1][:5]
    if ":" not in clock:
        return None
    hour, minute = clock.split(":", 1)
    if not hour.isdigit() or not minute.isdigit():
        return None
    return int(hour) * 60 + int(minute)


def _factor(name: str, label: str, score: float, max_score: float, detail: str) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "score": round(score, 2),
        "max_score": max_score,
        "detail": detail,
    }


def _bounded_score(value: float, full_credit_threshold: float, max_score: float) -> float:
    normalized = (value + full_credit_threshold) / (full_credit_threshold * 2)
    return min(max_score, max(0.0, normalized * max_score))


def _grade_trade_score(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def _trade_evaluation_summary(group: dict[str, Any], grade: str) -> str:
    pnl = float(group["pnl"] or 0)
    direction = "多头" if group["direction"] == "LONG" else "空头"
    if pnl > 0:
        return f"{direction}交易已实现盈利，综合评分 {grade}，重点复盘执行质量与清仓效率。"
    if pnl < 0:
        return f"{direction}交易已实现亏损，综合评分 {grade}，重点复盘入场位置、止损和量能确认。"
    return f"{direction}交易接近持平，综合评分 {grade}，重点复盘机会成本和出场纪律。"


def _closed_round_trip_pnls(fills: list[dict[str, Any]]) -> list[float]:
    states: dict[tuple[str, str], dict[str, float]] = {}
    realized: list[float] = []
    for fill in sorted(fills, key=lambda item: (item["account_canonical"], item["symbol"], item["filled_at"], item["id"])):
        key = (fill["account_canonical"], fill["symbol"])
        state = states.setdefault(key, {"position": 0.0, "cash": 0.0})
        _apply_fill_to_round_trip_state(state, fill, realized)
    return realized


def _apply_fill_to_round_trip_state(state: dict[str, float], fill: dict[str, Any], realized: list[float]) -> None:
    remaining_quantity = float(fill["quantity"])
    price = float(fill["price"])
    side_sign = 1.0 if fill["side"] == "BUY" else -1.0
    while remaining_quantity > 0:
        position = state["position"]
        if _is_flat(position) or (position > 0 and side_sign > 0) or (position < 0 and side_sign < 0):
            _open_or_add_position(state, side_sign, remaining_quantity, price)
            return

        close_quantity = min(abs(position), remaining_quantity)
        state["cash"] += _cash_delta(side_sign, close_quantity, price)
        state["position"] += side_sign * close_quantity
        remaining_quantity -= close_quantity
        if _is_flat(state["position"]):
            realized.append(round(state["cash"], 6))
            state["position"] = 0.0
            state["cash"] = 0.0


def _open_or_add_position(state: dict[str, float], side_sign: float, quantity: float, price: float) -> None:
    state["position"] += side_sign * quantity
    state["cash"] += _cash_delta(side_sign, quantity, price)


def _cash_delta(side_sign: float, quantity: float, price: float) -> float:
    return -quantity * price if side_sign > 0 else quantity * price


def _is_flat(position: float) -> bool:
    return abs(position) < 1e-9


def _dedupe_fill_read_model(fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    occurrences_by_batch: dict[tuple[str, tuple[Any, ...]], int] = {}
    latest_by_signature: dict[tuple[Any, ...], dict[str, Any]] = {}
    for fill in sorted(fills, key=lambda item: (item["_batch_uploaded_at"], item["source_batch_id"], item["id"])):
        semantic_key = _fill_semantic_key(fill)
        batch_occurrence_key = (fill["source_batch_id"], semantic_key)
        occurrence = occurrences_by_batch.get(batch_occurrence_key, 0) + 1
        occurrences_by_batch[batch_occurrence_key] = occurrence
        read_model_key = (*semantic_key, occurrence)
        latest_by_signature[read_model_key] = fill
    return sorted(latest_by_signature.values(), key=lambda fill: (fill["filled_at"], fill["id"]))


def _fill_semantic_key(fill: dict[str, Any]) -> tuple[Any, ...]:
    execution_id = fill.get("execution_id")
    if execution_id:
        return ("execution", fill["account_canonical"], execution_id)
    return (
        "fallback",
        fill["account_canonical"],
        fill["symbol"],
        fill["side"],
        fill["filled_at"],
        _numeric_signature(fill["quantity"]),
        _numeric_signature(fill["price"]),
    )


def _numeric_signature(value: Any) -> str:
    return f"{float(value):.12g}"


def _insert_import_row(conn: sqlite3.Connection, batch_id: str, parse_result: ParseResult, row: ParsedRow) -> None:
    import_row_id = new_id("row")
    normalized = row.normalized or {}
    conn.execute(
        """
        INSERT INTO import_rows (
            id, batch_id, raw_line_number, raw_text, raw_line_hash, parser_version,
            field_mapper_version, account_raw, account_canonical, parsed_payload_json,
            row_status, order_id, execution_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_row_id,
            batch_id,
            row.row_number,
            row.raw_text,
            row.raw_line_hash,
            parse_result.parser_version,
            parse_result.field_mapper_version,
            normalized.get("account_raw"),
            normalized.get("account_canonical"),
            dumps_json(row.parsed_payload),
            row.row_status,
            normalized.get("order_id"),
            normalized.get("execution_id"),
        ),
    )
    if row.row_status == "quarantine":
        _insert_quarantine(conn, batch_id, import_row_id, row)
        return

    order_record_id = _upsert_order(conn, batch_id, import_row_id, normalized)
    fill_record_id = _upsert_fill(conn, batch_id, import_row_id, normalized, row.raw_line_hash) if normalized.get("has_fill") else None
    conn.execute(
        "UPDATE import_rows SET order_record_id = ?, fill_record_id = ? WHERE id = ?",
        (order_record_id, fill_record_id, import_row_id),
    )


def _insert_quarantine(conn: sqlite3.Connection, batch_id: str, import_row_id: str, row: ParsedRow) -> None:
    conn.execute(
        """
        INSERT INTO quarantine_rows (
            id, batch_id, import_row_id, raw_line_number, raw_text,
            failed_field, reason_code, reason, repair_hint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("quarantine"),
            batch_id,
            import_row_id,
            row.row_number,
            row.raw_text,
            row.failed_field or "unknown",
            row.reason_code or "unknown",
            row.reason or "无法解析该行。",
            row.repair_hint or "请检查该行字段。",
        ),
    )


def _upsert_order(conn: sqlite3.Connection, batch_id: str, import_row_id: str, normalized: dict[str, Any]) -> str:
    key = f"{normalized['account_canonical']}:{normalized['order_id']}"
    existing = conn.execute("SELECT id FROM orders WHERE idempotency_key = ?", (key,)).fetchone()
    if existing:
        return existing["id"]
    order_id = new_id("order")
    conn.execute(
        """
        INSERT INTO orders (
            id, account_raw, account_canonical, symbol, side, order_id, order_status,
            submitted_at, source_batch_id, source_import_row_id, idempotency_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id,
            normalized["account_raw"],
            normalized["account_canonical"],
            normalized["symbol"],
            normalized["side"],
            normalized["order_id"],
            normalized["status"],
            normalized["timestamp"],
            batch_id,
            import_row_id,
            key,
        ),
    )
    return order_id


def _upsert_fill(
    conn: sqlite3.Connection,
    batch_id: str,
    import_row_id: str,
    normalized: dict[str, Any],
    raw_line_hash: str,
) -> str:
    execution_id = normalized.get("execution_id") or ""
    if execution_id:
        key = f"{normalized['account_canonical']}:exec:{execution_id}"
    else:
        key = ":".join(
            [
                normalized["account_canonical"],
                "fallback",
                batch_id,
                import_row_id,
                normalized["order_id"],
                normalized["symbol"],
                normalized["side"],
                normalized["timestamp"],
                normalized["quantity"],
                normalized["price"],
                raw_line_hash,
            ]
        )
    existing = conn.execute("SELECT id FROM fills WHERE idempotency_key = ?", (key,)).fetchone()
    if existing:
        return existing["id"]
    fill_id = new_id("fill")
    conn.execute(
        """
        INSERT INTO fills (
            id, account_raw, account_canonical, symbol, side, order_id, execution_id,
            filled_at, quantity, price, source_batch_id, source_import_row_id, idempotency_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fill_id,
            normalized["account_raw"],
            normalized["account_canonical"],
            normalized["symbol"],
            normalized["side"],
            normalized["order_id"],
            execution_id or None,
            normalized["timestamp"],
            float(normalized["quantity"]),
            float(normalized["price"]),
            batch_id,
            import_row_id,
            key,
        ),
    )
    return fill_id


def _public_batch(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        **batch,
        "batch_id": batch["id"],
        "row_count": int(batch["row_count"]),
        "accepted_rows": int(batch["accepted_rows"]),
        "quarantined_rows": int(batch["quarantined_rows"]),
        "duplicate": bool(batch.get("duplicate", False)),
    }


def _public_quarantine_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "quarantine_id": row["id"],
        "raw_line": row["raw_text"],
    }


def _public_fill(fill: dict[str, Any]) -> dict[str, Any]:
    public_fill = {key: value for key, value in fill.items() if not key.startswith("_")}
    return {
        **public_fill,
        "fill_id": fill["id"],
        "quantity": float(fill["quantity"]),
        "price": float(fill["price"]),
        "uses_fallback_idempotency_key": ":fallback:" in fill["idempotency_key"],
    }


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
