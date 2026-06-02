from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any


PARSER_VERSION = "stp_txt_parser_v0.1.0"
FIELD_MAPPER_VERSION = "stp_txt_mapping_v0.1.0"


FIELD_ALIASES = {
    "account": {"account", "acct", "accountid", "account_id", "accountno", "account_number"},
    "symbol": {"symbol", "sym", "ticker"},
    "side": {"side", "action", "buy_sell", "buysell", "b/s"},
    "order_id": {"order_id", "orderid", "orderno", "order_no", "clordid", "cl_ord_id"},
    "execution_id": {"execution_id", "exec_id", "execid", "executionid", "fill_id"},
    "quantity": {"quantity", "qty", "shares", "filled_qty", "fill_qty"},
    "price": {"price", "fill_price", "avg_price", "execution_price"},
    "timestamp": {"timestamp", "time", "datetime", "date_time", "filled_at", "submitted_at"},
    "status": {"status", "order_status", "state"},
}

REQUIRED_FIELDS = ("account", "symbol", "side", "order_id", "timestamp")

SIDE_MAP = {
    "B": "BUY",
    "BUY": "BUY",
    "BOT": "BUY",
    "BOUGHT": "BUY",
    "S": "SELL",
    "SLD": "SELL",
    "SELL": "SELL",
    "SOLD": "SELL",
    "SSHRT": "SELL",
    "SHORT": "SELL",
}

CANCELLED_STATUSES = {"CANCELLED", "CANCELED", "CXLD", "REJECTED"}


@dataclass(frozen=True)
class ParsedRow:
    row_number: int
    raw_text: str
    raw_line_hash: str
    row_status: str
    parsed_payload: dict[str, Any]
    normalized: dict[str, Any] | None = None
    failed_field: str | None = None
    reason_code: str | None = None
    reason: str | None = None
    repair_hint: str | None = None


@dataclass(frozen=True)
class ParseResult:
    parser_version: str
    field_mapper_version: str
    rows: list[ParsedRow] = field(default_factory=list)
    file_error: str | None = None
    repair_hint: str | None = None


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonicalize_account(value: str | None) -> str:
    return (value or "").strip().upper()


def parse_stp_txt(raw_bytes: bytes) -> ParseResult:
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ParseResult(
            parser_version=PARSER_VERSION,
            field_mapper_version=FIELD_MAPPER_VERSION,
            file_error="empty_file",
            repair_hint="请上传包含表头和至少一行订单或成交记录的 STP TXT 文件。",
        )

    delimiter = _detect_delimiter(lines[0])
    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    try:
        headers = next(reader)
    except StopIteration:
        return ParseResult(PARSER_VERSION, FIELD_MAPPER_VERSION, file_error="empty_file")

    header_map, unknown_columns = _build_header_map(headers)
    if not header_map:
        return ParseResult(
            parser_version=PARSER_VERSION,
            field_mapper_version=FIELD_MAPPER_VERSION,
            file_error="missing_header",
            repair_hint="请确认 TXT 第一行包含账号、symbol、方向、订单号和时间字段。",
        )

    rows: list[ParsedRow] = []
    for zero_based_index, values in enumerate(reader, start=2):
        raw_text = lines[zero_based_index - 1] if zero_based_index - 1 < len(lines) else delimiter.join(values)
        payload = _payload_from_values(headers, values)
        payload["_unknown_columns"] = unknown_columns
        rows.append(_parse_row(zero_based_index, raw_text, payload, header_map))

    if not rows:
        return ParseResult(
            parser_version=PARSER_VERSION,
            field_mapper_version=FIELD_MAPPER_VERSION,
            file_error="no_data_rows",
            repair_hint="请确认 TXT 表头后至少有一行订单或成交记录。",
        )

    return ParseResult(PARSER_VERSION, FIELD_MAPPER_VERSION, rows=rows)


def _detect_delimiter(header_line: str) -> str:
    if "\t" in header_line:
        return "\t"
    if "," in header_line:
        return ","
    return "\t"


def _normalize_header(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if ch.isalnum() or ch in {"/", "_"})


def _build_header_map(headers: list[str]) -> tuple[dict[str, str], list[str]]:
    canonical_by_alias: dict[str, str] = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            canonical_by_alias[_normalize_header(alias)] = canonical

    header_map: dict[str, str] = {}
    unknown: list[str] = []
    for header in headers:
        normalized = _normalize_header(header)
        canonical = canonical_by_alias.get(normalized)
        if canonical:
            header_map[canonical] = header
        else:
            unknown.append(header)
    return header_map, unknown


def _payload_from_values(headers: list[str], values: list[str]) -> dict[str, Any]:
    payload = {header: values[index].strip() if index < len(values) else "" for index, header in enumerate(headers)}
    if len(values) > len(headers):
        payload["_extra_values"] = values[len(headers) :]
    return payload


def _parse_row(row_number: int, raw_text: str, payload: dict[str, Any], header_map: dict[str, str]) -> ParsedRow:
    missing = [field for field in REQUIRED_FIELDS if not _get(payload, header_map, field)]
    if missing:
        return _quarantine(
            row_number,
            raw_text,
            payload,
            failed_field=",".join(missing),
            reason_code="missing_required_field",
            reason=f"缺少必填字段: {', '.join(missing)}",
            repair_hint="请补齐账号、symbol、方向、订单号和时间字段后重新导入。",
        )

    side_raw = _get(payload, header_map, "side")
    side = SIDE_MAP.get(side_raw.strip().upper())
    if not side:
        return _quarantine(
            row_number,
            raw_text,
            payload,
            failed_field="side",
            reason_code="invalid_side",
            reason=f"无法识别方向: {side_raw}",
            repair_hint="方向字段应能映射为 BUY 或 SELL。",
        )

    quantity_raw = _get(payload, header_map, "quantity")
    price_raw = _get(payload, header_map, "price")
    status = (_get(payload, header_map, "status") or "UNKNOWN").strip().upper()
    if status not in CANCELLED_STATUSES:
        missing_fill_fields = [field for field, value in (("quantity", quantity_raw), ("price", price_raw)) if not value]
        if missing_fill_fields:
            return _quarantine(
                row_number,
                raw_text,
                payload,
                failed_field=",".join(missing_fill_fields),
                reason_code="missing_required_field",
                reason=f"成交记录缺少字段: {', '.join(missing_fill_fields)}",
                repair_hint="FILLED/PARTIAL 成交行必须包含数量和价格。",
            )
    quantity = _parse_decimal(quantity_raw)
    price = _parse_decimal(price_raw)
    if quantity_raw and quantity is None:
        return _quarantine(row_number, raw_text, payload, "quantity", "invalid_quantity", "数量不是有效数字。", "请修正数量字段。")
    if price_raw and price is None:
        return _quarantine(row_number, raw_text, payload, "price", "invalid_price", "价格不是有效数字。", "请修正价格字段。")

    account_raw = _get(payload, header_map, "account")
    normalized = {
        "account_raw": account_raw,
        "account_canonical": canonicalize_account(account_raw),
        "symbol": _get(payload, header_map, "symbol").strip().upper(),
        "side": side,
        "order_id": _get(payload, header_map, "order_id").strip(),
        "execution_id": _get(payload, header_map, "execution_id").strip(),
        "quantity": str(quantity) if quantity is not None else "",
        "price": str(price) if price is not None else "",
        "timestamp": _get(payload, header_map, "timestamp").strip(),
        "status": status,
        "has_fill": bool(quantity is not None and price is not None and status not in CANCELLED_STATUSES),
    }
    return ParsedRow(
        row_number=row_number,
        raw_text=raw_text,
        raw_line_hash=sha256_text(raw_text),
        row_status="accepted",
        parsed_payload=payload,
        normalized=normalized,
    )


def _get(payload: dict[str, Any], header_map: dict[str, str], field: str) -> str:
    header = header_map.get(field)
    if not header:
        return ""
    value = payload.get(header, "")
    return str(value or "")


def _parse_decimal(value: str) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def _quarantine(
    row_number: int,
    raw_text: str,
    payload: dict[str, Any],
    failed_field: str,
    reason_code: str,
    reason: str,
    repair_hint: str,
) -> ParsedRow:
    return ParsedRow(
        row_number=row_number,
        raw_text=raw_text,
        raw_line_hash=sha256_text(raw_text),
        row_status="quarantine",
        parsed_payload=payload,
        failed_field=failed_field,
        reason_code=reason_code,
        reason=reason,
        repair_hint=repair_hint,
    )
