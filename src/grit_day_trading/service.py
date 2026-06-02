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
    if existing:
        summary = get_batch(conn, existing["id"])
        summary["duplicate"] = True
        return summary

    parse_result = parse_stp_txt(raw_bytes)
    batch_id = new_id("batch")
    if parse_result.file_error:
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
        SELECT f.*, r.raw_line_number, b.parser_version, b.field_mapper_version
        FROM fills f
        JOIN import_rows r ON r.id = f.source_import_row_id
        JOIN import_batches b ON b.id = f.source_batch_id
        {where}
        ORDER BY filled_at, id
        """,
        params,
    ).fetchall()
    return [_public_fill(row) for row in rows_to_dicts(rows)]


def daily_summary(conn: sqlite3.Connection, date: str) -> dict[str, Any]:
    fills = list_fills(conn, date=date)
    positions: dict[tuple[str, str], float] = {}
    pnl_by_key: dict[tuple[str, str], float] = {}
    for fill in fills:
        key = (fill["account_canonical"], fill["symbol"])
        signed_cash = float(fill["quantity"]) * float(fill["price"])
        if fill["side"] == "BUY":
            positions[key] = positions.get(key, 0.0) + float(fill["quantity"])
            pnl_by_key[key] = pnl_by_key.get(key, 0.0) - signed_cash
        else:
            positions[key] = positions.get(key, 0.0) - float(fill["quantity"])
            pnl_by_key[key] = pnl_by_key.get(key, 0.0) + signed_cash

    realized = list(pnl_by_key.values())
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
        "pnl": round(sum(realized), 6),
        "win_rate": round(win_rate, 6),
        "profit_factor": None if profit_factor is None else round(profit_factor, 6),
        "quarantine_row_count": quarantine_count,
        "source": "committed_fills_only",
    }


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
    return {
        **fill,
        "fill_id": fill["id"],
        "quantity": float(fill["quantity"]),
        "price": float(fill["price"]),
        "uses_fallback_idempotency_key": ":fallback:" in fill["idempotency_key"],
    }


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
