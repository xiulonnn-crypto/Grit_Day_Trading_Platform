from pathlib import Path

from grit_day_trading.parser import (
    FIELD_MAPPER_VERSION,
    PARSER_VERSION,
    canonicalize_account,
    parse_stp_txt,
    sha256_text,
)


def test_parser_keeps_versions_and_canonicalizes_accounts():
    raw = Path("tests/fixtures/stp_sample.tsv").read_bytes()

    result = parse_stp_txt(raw)

    assert result.parser_version == PARSER_VERSION
    assert result.field_mapper_version == FIELD_MAPPER_VERSION
    assert result.file_error is None
    accepted = [row for row in result.rows if row.row_status == "accepted"]
    quarantined = [row for row in result.rows if row.row_status == "quarantine"]
    assert len(accepted) == 3
    assert len(quarantined) == 1
    assert accepted[0].normalized["account_raw"] == "acct-01"
    assert accepted[0].normalized["account_canonical"] == "ACCT-01"
    assert accepted[0].parser_version == PARSER_VERSION
    assert accepted[0].field_mapper_version == FIELD_MAPPER_VERSION
    assert accepted[0].normalized["parser_version"] == PARSER_VERSION
    assert accepted[0].normalized["field_mapper_version"] == FIELD_MAPPER_VERSION
    assert quarantined[0].reason_code == "missing_required_field"


def test_empty_file_fails_at_file_level():
    result = parse_stp_txt(b"")

    assert result.file_error == "empty_file"
    assert result.rows == []


def test_unknown_columns_are_preserved_in_payload():
    raw = b"Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus\tMystery\nA\tMSFT\tB\tO1\tE1\t1\t2\t2026-06-01T09:30:00\tFILLED\tX\n"

    result = parse_stp_txt(raw)

    assert result.rows[0].row_status == "accepted"
    assert result.rows[0].parsed_payload["Mystery"] == "X"
    assert result.rows[0].parsed_payload["_unknown_columns"] == ["Mystery"]
    assert result.rows[0].parsed_payload["_field_mapping"]["field_mapper_version"] == FIELD_MAPPER_VERSION
    assert result.rows[0].parsed_payload["_field_mapping"]["unknown_columns"] == ["Mystery"]


def test_headerless_chinese_fill_rows_use_default_contract_and_synthetic_order_ids():
    raw = (
        "\n"
        "2026-06-01\t09:31:00\tAAPL\t买入\t100\t10.00\t acct-hk \tDMA\n"
        "01/06/2026\t10:15\tAAPL\t卖出\t100\t11.50\tACCT-HK\tDMA\n"
    ).encode()

    result = parse_stp_txt(raw)

    assert result.file_error is None
    assert len(result.rows) == 2
    first = result.rows[0]
    assert first.row_number == 2
    assert first.row_status == "accepted"
    assert first.normalized["account_raw"] == "acct-hk"
    assert first.normalized["account_canonical"] == "ACCT-HK"
    assert first.normalized["symbol"] == "AAPL"
    assert first.normalized["side"] == "BUY"
    assert first.normalized["timestamp"] == "2026-06-01T09:31:00"
    assert first.normalized["order_id"].startswith("ROW-")
    assert first.normalized["order_id_missing"] is True
    assert first.normalized["order_idempotency_basis"] == "fallback:raw_line_hash"
    assert first.normalized["execution_id_missing"] is True
    assert first.normalized["fill_idempotency_basis"].startswith("fallback:")
    assert first.parsed_payload["_field_mapping"]["header_source"] == "inferred_headerless_zh_fill"
    assert first.parsed_payload["_field_mapping"]["synthetic_fields"] == {
        "order_id": "raw_line_hash",
        "timestamp": "trade_date+trade_time",
    }
    assert result.rows[1].normalized["side"] == "SELL"
    assert result.rows[1].normalized["timestamp"] == "2026-06-01T10:15:00"


def test_headerless_utf16_comma_rows_can_keep_order_id_and_unknown_tail_column():
    raw_text = (
        "26/06/01,09:31:00,AAPL,BOT,100,10.00, acct-hk ,DMA,12345678,\n"
        "26/06/01,10:15:00,AAPL,SLD SHRT,100,11.50,ACCT-HK,DMA,12345679,note\n"
    )

    result = parse_stp_txt(raw_text.encode("utf-16le"))

    assert result.file_error is None
    assert len(result.rows) == 2
    first = result.rows[0]
    assert first.row_status == "accepted"
    assert first.normalized["order_id"] == "12345678"
    assert first.normalized["order_id_missing"] is False
    assert first.normalized["order_idempotency_basis"] == "account_canonical+order_id"
    assert first.normalized["side"] == "BUY"
    assert first.normalized["timestamp"] == "2026-06-01T09:31:00"
    assert first.parsed_payload["_field_mapping"]["header_source"] == "inferred_headerless_zh_fill"
    assert first.parsed_payload["_field_mapping"]["synthetic_fields"] == {"timestamp": "trade_date+trade_time"}
    assert first.parsed_payload["_unknown_columns"] == ["备注"]
    assert result.rows[1].normalized["side"] == "SELL"
    assert result.rows[1].normalized["timestamp"] == "2026-06-01T10:15:00"


def test_headerless_chinese_fill_row_with_missing_price_is_quarantined():
    raw = "2026-06-01\t09:31:00\tAAPL\t买入\t100\t\tacct-hk\tDMA\n".encode()

    result = parse_stp_txt(raw)

    assert result.file_error is None
    assert result.rows[0].row_status == "quarantine"
    assert result.rows[0].failed_field == "price"
    assert result.rows[0].reason_code == "missing_required_field"
    assert result.rows[0].parsed_payload["_field_mapping"]["header_source"] == "inferred_headerless_zh_fill"


def test_short_headerless_rows_still_fail_as_missing_header():
    raw = "2026-06-01\t09:31:00\tAAPL\t买入\t100\t10.00\tacct-hk\n".encode()

    result = parse_stp_txt(raw)

    assert result.file_error == "missing_header"
    assert result.rows == []


def test_account_canonicalization_contract():
    assert canonicalize_account(" acct-01 \n") == "ACCT-01"


def test_parser_handles_stp_aliases_order_only_rows_partial_fills_and_fallback_keys():
    raw = Path("tests/fixtures/stp_edge_cases.tsv").read_bytes()

    result = parse_stp_txt(raw)

    accepted = [row for row in result.rows if row.row_status == "accepted"]
    quarantined = [row for row in result.rows if row.row_status == "quarantine"]
    assert len(accepted) == 4
    assert len(quarantined) == 1

    partial = accepted[0].normalized
    assert partial["account_raw"] == "acct-02"
    assert partial["account_canonical"] == "ACCT-02"
    assert partial["side"] == "BUY"
    assert partial["status"] == "PARTIALLY_FILLED"
    assert partial["has_fill"] is True
    assert partial["fill_idempotency_basis"] == "account_canonical+execution_id"

    cross_day = accepted[1].normalized
    assert cross_day["timestamp"] == "2026-06-02T09:31:01"
    assert cross_day["side"] == "SELL"

    cancelled = accepted[2].normalized
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["has_fill"] is False
    assert cancelled["quantity"] == ""
    assert cancelled["price"] == ""
    assert cancelled["fill_idempotency_basis"] == "not_applicable"

    fallback_fill = accepted[3].normalized
    assert fallback_fill["has_fill"] is True
    assert fallback_fill["execution_id"] == ""
    assert fallback_fill["execution_id_missing"] is True
    assert fallback_fill["fill_idempotency_basis"].startswith("fallback:")

    assert quarantined[0].failed_field == "quantity"
    assert quarantined[0].reason_code == "invalid_quantity"


def test_parser_preserves_physical_line_number_and_raw_line_hash_after_blank_lines():
    raw = (
        b"\n"
        b"Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus\n"
        b"\n"
        b"A\tMSFT\tB\tO1\tE1\t1\t2\t2026-06-01T09:30:00\tFILLED\n"
    )

    result = parse_stp_txt(raw)

    assert result.rows[0].row_number == 4
    assert result.rows[0].raw_text == "A\tMSFT\tB\tO1\tE1\t1\t2\t2026-06-01T09:30:00\tFILLED"
    assert result.rows[0].raw_line_hash == sha256_text(result.rows[0].raw_text)


def test_extra_values_are_quarantined_instead_of_silently_committed():
    raw = b"Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus\nA\tMSFT\tB\tO1\tE1\t1\t2\t2026-06-01T09:30:00\tFILLED\tUNMAPPED\n"

    result = parse_stp_txt(raw)

    assert result.rows[0].row_status == "quarantine"
    assert result.rows[0].failed_field == "_extra_values"
    assert result.rows[0].reason_code == "extra_unmapped_values"
    assert result.rows[0].parsed_payload["_extra_values"] == ["UNMAPPED"]

