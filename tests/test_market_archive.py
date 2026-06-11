from pathlib import Path

from grit_day_trading.market_archive import (
    archive_yahoo_minutes_for_committed_fills,
    archive_yahoo_minutes_for_import_batch,
    archive_yahoo_minutes_for_symbol_group_window,
    archive_yahoo_minutes_for_symbol_window,
    list_market_minute_archives,
)
from grit_day_trading.market_provider import FakeMarketDataProvider, MarketBar
from grit_day_trading.service import import_stp_txt, list_fills
from grit_day_trading.storage import connect, initialize_database
from grit_day_trading.strategy import DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID, update_strategy_config


SAMPLE_PATH = Path("tests/fixtures/stp_sample.tsv")


def test_archive_yahoo_minutes_groups_committed_fill_symbols_by_trade_date(tmp_path):
    conn = _seed_db(tmp_path)
    provider = FakeMarketDataProvider(
        minute_bars={
            "AAPL": [
                MarketBar("2026-06-01T09:30:00", 99.5, 101.0, 99.0, 100.0, 100),
                MarketBar("2026-06-01T09:31:00", 100.5, 103.0, 100.0, 102.0, 300),
            ]
        }
    )
    try:
        summary = archive_yahoo_minutes_for_committed_fills(
            conn,
            trade_date="2026-06-01",
            provider=provider,
        )

        assert summary["status"] == "completed"
        assert summary["provider"] == "yahoo"
        assert summary["target_count"] == 1
        assert summary["available_count"] == 1
        archive = summary["items"][0]
        assert archive["provider"] == "yahoo"
        assert archive["symbol"] == "AAPL"
        assert archive["trade_date"] == "2026-06-01"
        assert archive["requested_start"] == "2026-06-01T04:00:00"
        assert archive["requested_end"] == "2026-06-01T20:00:00"
        assert archive["source_fill_count"] == 2
        assert archive["data_status"] == "available"
        assert archive["bar_count"] == 2
        assert archive["vwap"] == 101.5
        assert archive["day_high"] == 103.0
        assert archive["day_low"] == 99.0
        assert len(archive["bars_hash"]) == 64

        stored = list_market_minute_archives(conn, trade_date="2026-06-01")
        assert [item["archive_id"] for item in stored] == [archive["archive_id"]]
        assert conn.execute("SELECT COUNT(*) FROM market_data_provider_attempts").fetchone()[0] == 1
        assert [fill["price"] for fill in list_fills(conn, date="2026-06-01")] == [10.0, 11.5]
    finally:
        conn.close()


def test_archive_yahoo_minutes_includes_enabled_momentum_context_symbols(tmp_path):
    conn = _seed_db(tmp_path)
    provider = FakeMarketDataProvider(
        minute_bars={
            "AAPL": [MarketBar("2026-06-01T11:00:00", 99.5, 101.0, 99.0, 100.0, 100)],
            "QQQ": [MarketBar("2026-06-01T11:00:00", 400.0, 401.0, 399.0, 400.5, 1000)],
            "SMH": [MarketBar("2026-06-01T11:00:00", 250.0, 251.0, 249.0, 250.5, 1000)],
        }
    )
    try:
        update_strategy_config(conn, DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID, enabled=True)

        summary = archive_yahoo_minutes_for_committed_fills(
            conn,
            trade_date="2026-06-01",
            provider=provider,
        )
        repeated = archive_yahoo_minutes_for_committed_fills(
            conn,
            trade_date="2026-06-01",
            provider=provider,
        )

        by_symbol = {item["symbol"]: item for item in summary["items"]}
        assert summary["status"] == "completed"
        assert summary["target_count"] == 3
        assert set(by_symbol) == {"AAPL", "QQQ", "SMH"}
        assert by_symbol["AAPL"]["source_fill_count"] == 2
        assert by_symbol["QQQ"]["source_fill_count"] == 0
        assert by_symbol["SMH"]["source_fill_count"] == 0
        assert all(item["data_status"] == "available" for item in by_symbol.values())
        assert {item["archive_id"] for item in repeated["items"]} == {item["archive_id"] for item in summary["items"]}
        assert conn.execute("SELECT COUNT(*) FROM market_minute_archives").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM market_data_provider_attempts").fetchone()[0] == 3
    finally:
        conn.close()


def test_archive_yahoo_minutes_for_import_batch_scopes_to_batch_fill_symbols(tmp_path):
    db_path = tmp_path / "archive-batch.db"
    conn = connect(db_path)
    provider = FakeMarketDataProvider()
    try:
        initialize_database(conn)
        first = import_stp_txt(conn, "sample.tsv", SAMPLE_PATH.read_bytes())
        second = import_stp_txt(
            conn,
            "second.tsv",
            (
                "Account\tSymbol\tSide\tOrderID\tExecID\tQty\tPrice\tTime\tStatus\n"
                "acct-rt\tMSFT\tBOT\tO-200\tE-200\t10\t20.00\t2026-06-02T09:30:00\tFILLED\n"
            ).encode(),
        )

        summary = archive_yahoo_minutes_for_import_batch(conn, batch_id=second["batch_id"], provider=provider)
        repeated = archive_yahoo_minutes_for_import_batch(conn, batch_id=second["batch_id"], provider=provider)

        assert first["batch_id"] != second["batch_id"]
        assert summary["batch_id"] == second["batch_id"]
        assert summary["target_count"] == 1
        assert [(item["trade_date"], item["symbol"], item["source_fill_count"]) for item in summary["items"]] == [
            ("2026-06-02", "MSFT", 1)
        ]
        assert {item["archive_id"] for item in repeated["items"]} == {item["archive_id"] for item in summary["items"]}
        assert conn.execute("SELECT COUNT(*) FROM market_minute_archives").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM market_data_provider_attempts").fetchone()[0] == 1
        assert [fill["symbol"] for fill in list_fills(conn, date="2026-06-01")] == ["AAPL", "AAPL"]
    finally:
        conn.close()


def test_archive_yahoo_minutes_is_idempotent_without_force(tmp_path):
    conn = _seed_db(tmp_path)
    try:
        provider = FakeMarketDataProvider()
        first = archive_yahoo_minutes_for_committed_fills(conn, trade_date="2026-06-01", provider=provider)["items"][0]
        second = archive_yahoo_minutes_for_committed_fills(conn, trade_date="2026-06-01", provider=provider)["items"][0]

        assert second["archive_id"] == first["archive_id"]
        assert conn.execute("SELECT COUNT(*) FROM market_minute_archives").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM market_data_provider_attempts").fetchone()[0] == 1
    finally:
        conn.close()


def test_archive_yahoo_minutes_preserves_provider_failure_as_visible_archive(tmp_path):
    conn = _seed_db(tmp_path)
    provider = FakeMarketDataProvider(minute_status={"AAPL": "provider_failed"})
    try:
        summary = archive_yahoo_minutes_for_committed_fills(
            conn,
            trade_date="2026-06-01",
            provider=provider,
        )

        archive = summary["items"][0]
        assert summary["provider_failed_count"] == 1
        assert archive["data_status"] == "provider_failed"
        assert archive["failure_reason"] == "fake_provider_failed"
        assert archive["bar_count"] == 0
        attempt = conn.execute("SELECT * FROM market_data_provider_attempts").fetchone()
        assert attempt["request_type"] == "archive_minute_bars"
        assert attempt["status"] == "failed"
    finally:
        conn.close()


def test_archive_yahoo_minutes_returns_no_targets_without_committed_fills(tmp_path):
    conn = _seed_db(tmp_path)
    try:
        summary = archive_yahoo_minutes_for_committed_fills(conn, trade_date="2026-06-03")

        assert summary["status"] == "no_targets"
        assert summary["target_count"] == 0
        assert summary["items"] == []
        assert conn.execute("SELECT COUNT(*) FROM market_data_provider_attempts").fetchone()[0] == 0
    finally:
        conn.close()


def test_archive_yahoo_minutes_for_symbol_window_does_not_require_committed_fills(tmp_path):
    conn = _seed_db(tmp_path)
    provider = FakeMarketDataProvider()
    try:
        summary = archive_yahoo_minutes_for_symbol_window(
            conn,
            symbol="msft",
            end_date="2026-06-05",
            window_trading_days=3,
            provider=provider,
        )

        assert summary["status"] == "completed"
        assert summary["symbol"] == "MSFT"
        assert summary["requested_trade_dates"] == ["2026-06-03", "2026-06-04", "2026-06-05"]
        assert summary["target_count"] == 3
        assert summary["selected_symbol_available_count"] == 3
        assert {item["symbol"] for item in summary["items"]} == {"MSFT"}
        assert {item["source_fill_count"] for item in summary["items"]} == {0}
        assert len(list_market_minute_archives(conn, symbol="MSFT", provider="yahoo")) == 3
        assert [fill["symbol"] for fill in list_fills(conn, date="2026-06-01")] == ["AAPL", "AAPL"]
    finally:
        conn.close()


def test_archive_yahoo_minutes_for_symbol_window_uses_calendar_days(tmp_path):
    conn = _seed_db(tmp_path)
    provider = FakeMarketDataProvider()
    try:
        summary = archive_yahoo_minutes_for_symbol_window(
            conn,
            symbol="msft",
            end_date="2026-06-08",
            window_trading_days=3,
            provider=provider,
        )

        assert summary["requested_trade_dates"] == ["2026-06-06", "2026-06-07", "2026-06-08"]
        assert summary["target_count"] == 3
        assert [item["trade_date"] for item in summary["items"]] == ["2026-06-06", "2026-06-07", "2026-06-08"]
    finally:
        conn.close()


def test_archive_yahoo_minutes_for_symbol_window_includes_momentum_context_when_enabled(tmp_path):
    conn = _seed_db(tmp_path)
    provider = FakeMarketDataProvider()
    try:
        update_strategy_config(conn, DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID, enabled=True)

        summary = archive_yahoo_minutes_for_symbol_window(
            conn,
            symbol="aapl",
            end_date="2026-06-02",
            window_trading_days=2,
            provider=provider,
        )

        assert summary["requested_trade_dates"] == ["2026-06-01", "2026-06-02"]
        assert summary["target_count"] == 6
        assert {(item["trade_date"], item["symbol"]) for item in summary["items"]} == {
            ("2026-06-01", "AAPL"),
            ("2026-06-01", "QQQ"),
            ("2026-06-01", "SMH"),
            ("2026-06-02", "AAPL"),
            ("2026-06-02", "QQQ"),
            ("2026-06-02", "SMH"),
        }
    finally:
        conn.close()


def test_archive_yahoo_minutes_for_symbol_group_window_persists_research_symbols(tmp_path):
    conn = _seed_db(tmp_path)
    provider = FakeMarketDataProvider()
    try:
        summary = archive_yahoo_minutes_for_symbol_group_window(
            conn,
            symbols=["mu", "NVDA", "SPY", "mu"],
            end_date="2026-06-05",
            window_trading_days=2,
            provider=provider,
        )
        repeated = archive_yahoo_minutes_for_symbol_group_window(
            conn,
            symbols=["MU", "NVDA", "SPY"],
            end_date="2026-06-05",
            window_trading_days=2,
            provider=provider,
        )

        assert summary["status"] == "completed"
        assert summary["symbols"] == ["MU", "NVDA", "SPY"]
        assert summary["requested_trade_dates"] == ["2026-06-04", "2026-06-05"]
        assert summary["target_count"] == 6
        assert summary["selected_symbol_available_count"] == 6
        assert summary["per_symbol"]["MU"]["available_count"] == 2
        assert summary["per_symbol"]["NVDA"]["available_count"] == 2
        assert summary["per_symbol"]["SPY"]["available_count"] == 2
        assert {(item["trade_date"], item["symbol"]) for item in summary["items"]} == {
            ("2026-06-04", "MU"),
            ("2026-06-04", "NVDA"),
            ("2026-06-04", "SPY"),
            ("2026-06-05", "MU"),
            ("2026-06-05", "NVDA"),
            ("2026-06-05", "SPY"),
        }
        assert {item["archive_id"] for item in repeated["items"]} == {item["archive_id"] for item in summary["items"]}
        assert conn.execute("SELECT COUNT(*) FROM market_minute_archives").fetchone()[0] == 6
        assert [fill["symbol"] for fill in list_fills(conn, date="2026-06-01")] == ["AAPL", "AAPL"]
    finally:
        conn.close()


def _seed_db(tmp_path):
    conn = connect(tmp_path / "archive.db")
    initialize_database(conn)
    import_stp_txt(conn, "sample.tsv", SAMPLE_PATH.read_bytes())
    return conn
