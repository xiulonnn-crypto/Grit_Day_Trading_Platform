from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .parser import FIELD_MAPPER_VERSION, PARSER_VERSION, ParseResult, ParsedRow, parse_stp_txt
from .storage import dumps_json, new_id, row_to_dict, rows_to_dicts


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
    fills = list_fills(conn, date=date)
    buy_qty_by_key: dict[tuple[str, str], float] = {}
    sell_qty_by_key: dict[tuple[str, str], float] = {}
    for fill in fills:
        key = (fill["account_canonical"], fill["symbol"])
        quantity = float(fill["quantity"])
        if fill["side"] == "BUY":
            buy_qty_by_key[key] = buy_qty_by_key.get(key, 0.0) + quantity
        else:
            sell_qty_by_key[key] = sell_qty_by_key.get(key, 0.0) + quantity

    realized = _closed_round_trip_pnls(fills)
    trade_keys = set(buy_qty_by_key) | set(sell_qty_by_key)
    traded_quantity = sum(min(buy_qty_by_key.get(key, 0.0), sell_qty_by_key.get(key, 0.0)) for key in trade_keys)
    wins = [value for value in realized if value > 0]
    losses = [value for value in realized if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    win_rate = (len(wins) / len(realized)) if realized else 0.0
    profit_factor = None if gross_loss == 0 else gross_profit / gross_loss
    batch_ids = sorted({fill["source_batch_id"] for fill in fills})
    quarantine_count = 0
    if batch_ids:
        placeholders = ",".join("?" for _ in batch_ids)
        quarantine_count = conn.execute(
            f"SELECT COUNT(*) AS count FROM quarantine_rows WHERE batch_id IN ({placeholders})",
            batch_ids,
        ).fetchone()["count"]
    return {
        "date": date,
        "fill_count": len(fills),
        "trade_group_count": len(realized),
        "traded_quantity": _round_quantity(traded_quantity),
        "pnl": round(sum(realized), 6),
        "win_rate": round(win_rate, 6),
        "profit_factor": None if profit_factor is None else round(profit_factor, 6),
        "quarantine_row_count": quarantine_count,
        "source": "committed_fills_only",
    }


def _should_reparse_existing_batch(existing: sqlite3.Row) -> bool:
    version_drifted = existing["parser_version"] != PARSER_VERSION or existing["field_mapper_version"] != FIELD_MAPPER_VERSION
    if not version_drifted:
        return False
    if existing["status"] == "failed" and int(existing["row_count"]) == 0:
        return True
    return existing["status"] == "committed"


def _round_quantity(value: float) -> int | float:
    return int(value) if value.is_integer() else round(value, 6)


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
