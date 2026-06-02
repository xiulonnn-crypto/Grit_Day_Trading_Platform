from pathlib import Path

from grit_day_trading.parser import FIELD_MAPPER_VERSION, PARSER_VERSION, canonicalize_account, parse_stp_txt


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


def test_account_canonicalization_contract():
    assert canonicalize_account(" acct-01 \n") == "ACCT-01"

