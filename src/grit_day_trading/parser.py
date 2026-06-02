from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


PARSER_VERSION = "stp_txt_parser_v0.3.1"
FIELD_MAPPER_VERSION = "stp_txt_mapping_v0.3.1"

HEADERLESS_FILL_HEADERS = ["日期", "时间", "标的", "买卖", "股数", "价格", "账号", "通道"]
HEADERLESS_FILL_HEADER_VARIANTS = {
    8: HEADERLESS_FILL_HEADERS,
    9: [*HEADERLESS_FILL_HEADERS, "OrderID"],
    10: [*HEADERLESS_FILL_HEADERS, "OrderID", "备注"],
}
SYNTHETIC_TIMESTAMP_HEADER = "__synthetic_timestamp"
SYNTHETIC_ORDER_ID_HEADER = "__synthetic_order_id"


FIELD_ALIASES = {
    "account": {"account", "acct", "acctid", "acct_id", "accountid", "account_id", "accountno", "account_number", "账号", "账户"},
    "symbol": {"symbol", "sym", "ticker", "security", "security_symbol", "标的", "证券", "代码"},
    "side": {"side", "action", "buy_sell", "buysell", "b/s", "买卖", "方向"},
    "order_id": {"order_id", "orderid", "order_number", "ordernumber", "orderno", "order_no", "clordid", "cl_ord_id"},
    "execution_id": {"execution_id", "exec_id", "execid", "executionid", "execution_number", "fill_id"},
    "quantity": {"quantity", "qty", "shares", "filled_qty", "filled_quantity", "fill_qty", "股数", "数量", "成交股数"},
    "price": {"price", "fill_price", "avg_price", "execution_price", "exec_price", "价格", "成交价格", "成交价"},
    "timestamp": {
        "timestamp",
        "time",
        "datetime",
        "date_time",
        "日期时间",
        "成交时间",
        "filled_at",
        "filled_time",
        "execution_time",
        "submitted_at",
        "transact_time",
    },
    "status": {"status", "order_status", "state"},
    "trade_date": {"trade_date", "execution_date", "filled_date", "成交日期", "日期"},
    "trade_time": {"clock_time", "time_of_day", "成交时刻", "时间"},
    "channel": {"channel", "route", "routing", "desk", "通道"},
}

REQUIRED_FIELDS = ("account", "symbol", "side", "order_id", "timestamp")

SIDE_MAP = {
    "B": "BUY",
    "BUY": "BUY",
    "BOT": "BUY",
    "BOUGHT": "BUY",
    "买": "BUY",
    "买入": "BUY",
    "S": "SELL",
    "SLD": "SELL",
    "SLD_SHRT": "SELL",
    "SLDSHRT": "SELL",
    "SELL": "SELL",
    "SOLD": "SELL",
    "SSHRT": "SELL",
    "SHORT": "SELL",
    "SELL_SHORT": "SELL",
    "SELLSHORT": "SELL",
    "卖": "SELL",
    "卖出": "SELL",
}

CANCELLED_STATUSES = {"CANCELLED", "CANCELED", "CXLD", "REJECTED"}
ORDER_ONLY_STATUSES = CANCELLED_STATUSES | {
    "NEW",
    "OPEN",
    "WORKING",
    "PENDING",
    "PENDING_NEW",
    "PENDING_CANCEL",
    "EXPIRED",
}
FILL_STATUSES = {"FILLED", "FILL", "PARTIAL", "PARTIAL_FILL", "PARTIALLY_FILLED", "EXECUTED"}


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
    parser_version: str = PARSER_VERSION
    field_mapper_version: str = FIELD_MAPPER_VERSION


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
    text = _decode_text(raw_bytes)
    raw_lines = text.splitlines()
    header_index = next((index for index, line in enumerate(raw_lines) if line.strip()), None)
    if header_index is None:
        return ParseResult(
            parser_version=PARSER_VERSION,
            field_mapper_version=FIELD_MAPPER_VERSION,
            file_error="empty_file",
            repair_hint="请上传包含表头和至少一行订单或成交记录的 STP TXT 文件。",
        )

    header_line = raw_lines[header_index]
    delimiter = _detect_delimiter(header_line)
    reader = csv.reader(io.StringIO(header_line), delimiter=delimiter)
    try:
        headers = next(reader)
    except StopIteration:
        return ParseResult(PARSER_VERSION, FIELD_MAPPER_VERSION, file_error="empty_file")

    header_map, unknown_columns = _build_header_map(headers)
    data_start_index = header_index + 1
    header_source = "file_header"
    allow_synthetic_order_id = _is_headerless_fill_header_contract(headers) and "order_id" not in header_map
    if not header_map:
        inferred_headers = _infer_headerless_fill_headers(headers)
        if inferred_headers:
            headers = inferred_headers
            header_map, unknown_columns = _build_header_map(headers)
            data_start_index = header_index
            header_source = "inferred_headerless_zh_fill"
            allow_synthetic_order_id = "order_id" not in header_map
        else:
            return ParseResult(
                parser_version=PARSER_VERSION,
                field_mapper_version=FIELD_MAPPER_VERSION,
                file_error="missing_header",
                repair_hint="请确认 TXT 第一行包含账号、symbol、方向、订单号和时间字段；无表头 8 列成交 TXT 会按日期、时间、标的、买卖、股数、价格、账号、通道解析。",
            )

    header_map = _augment_header_map(header_map, allow_synthetic_order_id)

    rows: list[ParsedRow] = []
    for file_line_number, raw_text in enumerate(raw_lines[data_start_index:], start=data_start_index + 1):
        if not raw_text.strip():
            continue
        values = _read_row(raw_text, delimiter)
        payload = _payload_from_values(headers, values)
        _apply_synthetic_fields(payload, header_map, raw_text)
        _attach_mapping_diagnostics(payload, header_map, unknown_columns, header_source)
        rows.append(_parse_row(file_line_number, raw_text, payload, header_map))

    if not rows:
        return ParseResult(
            parser_version=PARSER_VERSION,
            field_mapper_version=FIELD_MAPPER_VERSION,
            file_error="no_data_rows",
            repair_hint="请确认 TXT 表头后至少有一行订单或成交记录。",
        )

    return ParseResult(PARSER_VERSION, FIELD_MAPPER_VERSION, rows=rows)


def _decode_text(raw_bytes: bytes) -> str:
    if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw_bytes.decode("utf-16", errors="replace")
    sample = raw_bytes[: min(len(raw_bytes), 512)]
    if sample.count(b"\x00") > max(1, len(sample) // 4):
        even_nulls = sum(1 for index in range(0, len(sample), 2) if sample[index] == 0)
        odd_nulls = sum(1 for index in range(1, len(sample), 2) if sample[index] == 0)
        if odd_nulls > even_nulls:
            return raw_bytes.decode("utf-16le", errors="replace")
        if even_nulls > odd_nulls:
            return raw_bytes.decode("utf-16be", errors="replace")
    return raw_bytes.decode("utf-8-sig", errors="replace")


def _detect_delimiter(header_line: str) -> str:
    delimiter_counts = {delimiter: header_line.count(delimiter) for delimiter in ("\t", ",", "|", ";")}
    delimiter, count = max(delimiter_counts.items(), key=lambda item: item[1])
    return delimiter if count else "\t"


def _read_row(raw_text: str, delimiter: str) -> list[str]:
    reader = csv.reader(io.StringIO(raw_text), delimiter=delimiter)
    return next(reader, [])


def _normalize_header(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if ch.isalnum() or ch == "/")


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


def _is_headerless_fill_header_contract(headers: list[str]) -> bool:
    normalized = [_normalize_header(header) for header in headers]
    expected_variants = {tuple(_normalize_header(header) for header in variant) for variant in HEADERLESS_FILL_HEADER_VARIANTS.values()}
    return tuple(normalized) in expected_variants


def _infer_headerless_fill_headers(values: list[str]) -> list[str] | None:
    headers = HEADERLESS_FILL_HEADER_VARIANTS.get(len(values))
    if not headers:
        return None
    date_value, time_value, symbol, side, quantity, price, account, _channel = [value.strip() for value in values[:8]]
    quantity_is_valid_or_missing = not quantity or _parse_decimal(quantity) is not None
    price_is_valid_or_missing = not price or _parse_decimal(price) is not None
    if all((date_value, time_value, symbol, account)) and SIDE_MAP.get(_normalize_token(side)) is not None and quantity_is_valid_or_missing and price_is_valid_or_missing:
        return headers
    return None


def _augment_header_map(header_map: dict[str, str], allow_synthetic_order_id: bool) -> dict[str, str]:
    augmented = dict(header_map)
    if "timestamp" not in augmented and "trade_date" in augmented and "trade_time" in augmented:
        augmented["timestamp"] = SYNTHETIC_TIMESTAMP_HEADER
    if allow_synthetic_order_id and "order_id" not in augmented:
        augmented["order_id"] = SYNTHETIC_ORDER_ID_HEADER
    return augmented


def _payload_from_values(headers: list[str], values: list[str]) -> dict[str, Any]:
    payload = {header: values[index].strip() if index < len(values) else "" for index, header in enumerate(headers)}
    if len(values) > len(headers):
        payload["_extra_values"] = [value.strip() for value in values[len(headers) :]]
    return payload


def _apply_synthetic_fields(payload: dict[str, Any], header_map: dict[str, str], raw_text: str) -> None:
    synthetic_fields: dict[str, str] = {}
    if header_map.get("timestamp") == SYNTHETIC_TIMESTAMP_HEADER:
        payload[SYNTHETIC_TIMESTAMP_HEADER] = _compose_timestamp(_get(payload, header_map, "trade_date"), _get(payload, header_map, "trade_time"))
        synthetic_fields["timestamp"] = "trade_date+trade_time"
    if header_map.get("order_id") == SYNTHETIC_ORDER_ID_HEADER:
        payload[SYNTHETIC_ORDER_ID_HEADER] = f"ROW-{sha256_text(raw_text)[:16]}"
        synthetic_fields["order_id"] = "raw_line_hash"
    if synthetic_fields:
        payload["_synthetic_fields"] = synthetic_fields


def _attach_mapping_diagnostics(payload: dict[str, Any], header_map: dict[str, str], unknown_columns: list[str], header_source: str) -> None:
    payload["_unknown_columns"] = unknown_columns
    payload["_parser_version"] = PARSER_VERSION
    payload["_field_mapping"] = {
        "field_mapper_version": FIELD_MAPPER_VERSION,
        "mapped_fields": sorted(header_map),
        "unknown_columns": unknown_columns,
        "header_source": header_source,
        "synthetic_fields": payload.get("_synthetic_fields", {}),
    }


def _parse_row(row_number: int, raw_text: str, payload: dict[str, Any], header_map: dict[str, str]) -> ParsedRow:
    if payload.get("_extra_values"):
        return _quarantine(
            row_number,
            raw_text,
            payload,
            failed_field="_extra_values",
            reason_code="extra_unmapped_values",
            reason="该行包含超过表头数量的额外字段值。",
            repair_hint="请确认 TXT 分隔符和字段映射，避免未命名值进入导入结果。",
        )

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
    side = SIDE_MAP.get(_normalize_token(side_raw))
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
    status = _normalize_status(_get(payload, header_map, "status"))
    has_quantity = bool(quantity_raw.strip())
    has_price = bool(price_raw.strip())
    should_have_fill_values = (
        status in FILL_STATUSES
        or (status == "UNKNOWN" and (has_quantity or has_price))
        or (status not in ORDER_ONLY_STATUSES and (has_quantity or has_price))
    )
    if should_have_fill_values:
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
    elif status not in ORDER_ONLY_STATUSES and (not has_quantity and not has_price):
        return _quarantine(
            row_number,
            raw_text,
            payload,
            failed_field="status",
            reason_code="unsupported_order_status",
            reason=f"无法判断该状态是否代表成交或订单: {status}",
            repair_hint="请补充可识别的订单状态，或提供数量和价格让该行按成交处理。",
        )
    quantity = _parse_decimal(quantity_raw)
    price = _parse_decimal(price_raw)
    if quantity_raw and quantity is None:
        return _quarantine(row_number, raw_text, payload, "quantity", "invalid_quantity", "数量不是有效数字。", "请修正数量字段。")
    if price_raw and price is None:
        return _quarantine(row_number, raw_text, payload, "price", "invalid_price", "价格不是有效数字。", "请修正价格字段。")

    account_raw = _get(payload, header_map, "account")
    execution_id = _get(payload, header_map, "execution_id").strip()
    has_fill = bool(quantity is not None and price is not None and status not in ORDER_ONLY_STATUSES)
    order_id_was_synthesized = "order_id" in payload.get("_synthetic_fields", {})
    normalized = {
        "account_raw": account_raw,
        "account_canonical": canonicalize_account(account_raw),
        "symbol": _get(payload, header_map, "symbol").strip().upper(),
        "side": side,
        "order_id": _get(payload, header_map, "order_id").strip(),
        "execution_id": execution_id,
        "quantity": str(quantity) if quantity is not None else "",
        "price": str(price) if price is not None else "",
        "timestamp": _get(payload, header_map, "timestamp").strip(),
        "status": status,
        "has_fill": has_fill,
        "order_idempotency_basis": "fallback:raw_line_hash" if order_id_was_synthesized else "account_canonical+order_id",
        "fill_idempotency_basis": (
            "not_applicable"
            if not has_fill
            else (
                "account_canonical+execution_id"
                if execution_id
                else "fallback:source_import_row+raw_line_hash"
            )
        ),
        "order_id_missing": order_id_was_synthesized,
        "execution_id_missing": bool(has_fill and not execution_id),
        "parser_version": PARSER_VERSION,
        "field_mapper_version": FIELD_MAPPER_VERSION,
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


def _normalize_token(value: str) -> str:
    return "_".join("".join(ch if ch.isalnum() else "_" for ch in value.strip().upper()).split("_"))


def _normalize_status(value: str) -> str:
    status = _normalize_token(value or "")
    return status or "UNKNOWN"


def _compose_timestamp(date_value: str, time_value: str) -> str:
    date_part = _normalize_date(date_value)
    time_part = _normalize_time(time_value)
    if date_part and time_part:
        return f"{date_part}T{time_part}"
    if date_value.strip() and time_value.strip():
        return f"{date_value.strip()}T{time_value.strip()}"
    return date_value.strip() or time_value.strip()


def _normalize_date(value: str) -> str:
    stripped = value.strip()
    slash_parts = stripped.split("/")
    if len(slash_parts) == 3 and all(part.isdigit() for part in slash_parts) and all(len(part) == 2 for part in slash_parts):
        first, middle, last = (int(part) for part in slash_parts)
        if first >= 20 and 1 <= middle <= 12 and 1 <= last <= 31:
            try:
                return datetime.strptime(stripped, "%y/%m/%d").date().isoformat()
            except ValueError:
                pass
        if last >= 20 and 1 <= middle <= 12 and 1 <= first <= 31:
            try:
                return datetime.strptime(stripped, "%d/%m/%y").date().isoformat()
            except ValueError:
                pass
    for date_format in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%m/%d/%y", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(stripped, date_format).date().isoformat()
        except ValueError:
            continue
    return stripped


def _normalize_time(value: str) -> str:
    stripped = value.strip()
    for time_format in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
        try:
            return datetime.strptime(stripped.upper(), time_format).time().replace(microsecond=0).isoformat()
        except ValueError:
            continue
    return stripped


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
