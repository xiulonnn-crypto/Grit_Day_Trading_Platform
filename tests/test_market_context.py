from pathlib import Path

from grit_day_trading.market_context import get_market_context_for_fill, replay_market_context
from grit_day_trading.market_provider import FakeMarketDataProvider, MarketBar
from grit_day_trading.service import import_stp_txt, list_fills
from grit_day_trading.storage import connect, initialize_database


SAMPLE_PATH = Path("tests/fixtures/stp_sample.tsv")


def test_replay_market_context_computes_snapshot_from_provider_bars(tmp_path):
    conn = _seed_db(tmp_path)
    try:
        fill = list_fills(conn, date="2026-06-01")[0]
        provider = FakeMarketDataProvider(
            minute_bars={
                "AAPL": [
                    MarketBar("2026-06-01T09:30:00", 99.5, 101.0, 99.0, 100.0, 100),
                    MarketBar("2026-06-01T09:31:00", 100.5, 103.0, 100.0, 102.0, 300),
                    MarketBar("2026-06-01T09:32:00", 101.5, 102.5, 101.0, 102.0, 100),
                ]
            }
        )

        snapshot = replay_market_context(
            conn,
            fill_id=fill["fill_id"],
            provider=provider,
            minutes_before=1,
            minutes_after=1,
        )

        assert snapshot["fill_id"] == fill["fill_id"]
        assert snapshot["provider"] == "fake"
        assert snapshot["symbol"] == "AAPL"
        assert snapshot["data_status"] == "available"
        assert snapshot["bar_count"] == 3
        assert snapshot["requested_start"] == "2026-06-01T09:30:00"
        assert snapshot["requested_end"] == "2026-06-01T09:32:00"
        assert snapshot["vwap"] == 101.6
        assert snapshot["day_high"] == 103.0
        assert snapshot["day_low"] == 99.0
        assert len(snapshot["bars_hash"]) == 64
        assert snapshot["volume_context"]["total_volume"] == 500.0

        loaded = get_market_context_for_fill(conn, fill["fill_id"])
        assert loaded["snapshot_id"] == snapshot["snapshot_id"]
    finally:
        conn.close()


def test_replay_market_context_is_idempotent_without_force(tmp_path):
    conn = _seed_db(tmp_path)
    try:
        fill_id = list_fills(conn, date="2026-06-01")[0]["fill_id"]

        first = replay_market_context(conn, fill_id=fill_id, minutes_before=1, minutes_after=1)
        second = replay_market_context(conn, fill_id=fill_id, minutes_before=1, minutes_after=1)

        assert second["snapshot_id"] == first["snapshot_id"]
        assert conn.execute("SELECT COUNT(*) FROM market_context_snapshots").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM market_data_provider_attempts").fetchone()[0] == 1
    finally:
        conn.close()


def test_replay_market_context_surfaces_non_success_provider_statuses(tmp_path):
    expected = {
        "partial": ("partial", "partial_provider_window"),
        "missing": ("missing", "no_bars_returned"),
        "provider_failed": ("provider_failed", "fake_provider_failed"),
        "timezone_conflict": ("timezone_conflict", "provider_timezone_conflict"),
    }

    for provider_status, (data_status, failure_reason) in expected.items():
        conn = _seed_db(tmp_path / provider_status)
        try:
            fill_id = list_fills(conn, date="2026-06-01")[0]["fill_id"]
            provider = FakeMarketDataProvider(minute_status={"AAPL": provider_status})

            snapshot = replay_market_context(
                conn,
                fill_id=fill_id,
                provider=provider,
                minutes_before=2,
                minutes_after=2,
            )

            assert snapshot["data_status"] == data_status
            assert snapshot["failure_reason"] == failure_reason
            if data_status != "partial":
                assert snapshot["bar_count"] == 0
                assert snapshot["vwap"] is None
            assert conn.execute("SELECT COUNT(*) FROM market_data_provider_attempts").fetchone()[0] == 1
        finally:
            conn.close()


def _seed_db(tmp_path):
    conn = connect(tmp_path / "trading.db")
    initialize_database(conn)
    import_stp_txt(conn, "sample.tsv", SAMPLE_PATH.read_bytes())
    return conn
