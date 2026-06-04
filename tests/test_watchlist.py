from grit_day_trading.market_provider import FakeMarketDataProvider, WatchlistCandidate
from grit_day_trading.storage import connect, initialize_database
from grit_day_trading.watchlist import WATCHLIST_RULES_VERSION, generate_watchlist, get_watchlist


def test_generate_watchlist_ranks_candidates_and_persists_reason_metrics(tmp_path):
    conn = connect(tmp_path / "watchlist.db")
    try:
        initialize_database(conn)
        provider = FakeMarketDataProvider(
            watchlist_candidates=[
                WatchlistCandidate("MSFT", {"relative_volume": 1.6, "gap_percent": 0.5, "price_change_percent": 3.2}),
                WatchlistCandidate("NVDA", {"relative_volume": 2.2, "gap_percent": 3.0, "price_change_percent": 4.0}),
                WatchlistCandidate("AAPL", {"relative_volume": 1.1, "gap_percent": 0.2, "price_change_percent": 0.5}),
            ]
        )

        run = generate_watchlist(conn, trade_date="2026-06-01", provider=provider)

        assert run["status"] == "completed"
        assert run["rules_version"] == WATCHLIST_RULES_VERSION
        assert run["item_count"] == 2
        assert [item["symbol"] for item in run["items"]] == ["NVDA", "MSFT"]
        assert run["items"][0]["reason_codes"] == ["relative_volume_spike", "gap_up", "momentum"]
        assert run["items"][0]["metrics"]["relative_volume"] == 2.2
        assert len(run["items"][0]["metrics_hash"]) == 64
        assert all(item["reason_codes_json"] for item in run["items"])
        assert all(item["metrics_json"] for item in run["items"])
    finally:
        conn.close()


def test_generate_watchlist_is_idempotent_and_force_replaces_items(tmp_path):
    conn = connect(tmp_path / "watchlist.db")
    try:
        initialize_database(conn)

        first = generate_watchlist(conn, trade_date="2026-06-01")
        second = generate_watchlist(conn, trade_date="2026-06-01")

        assert second["run_id"] == first["run_id"]
        assert conn.execute("SELECT COUNT(*) FROM watchlist_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM watchlist_items").fetchone()[0] == first["item_count"]

        empty_provider = FakeMarketDataProvider(watchlist_candidates=[])
        forced = generate_watchlist(conn, trade_date="2026-06-01", force=True, provider=empty_provider)
        assert forced["run_id"] == first["run_id"]
        assert forced["item_count"] == 0
        assert forced["items"] == []
    finally:
        conn.close()


def test_watchlist_provider_failure_leaves_a_visible_failed_run(tmp_path):
    conn = connect(tmp_path / "watchlist.db")
    try:
        initialize_database(conn)
        provider = FakeMarketDataProvider(watchlist_status="provider_failed")

        run = generate_watchlist(conn, trade_date="2026-06-01", provider=provider)

        assert run["status"] == "failed"
        assert run["failure_reason"] == "fake_watchlist_provider_failed"
        assert run["item_count"] == 0
        assert run["items"] == []
    finally:
        conn.close()


def test_get_watchlist_returns_empty_read_model_before_generation(tmp_path):
    conn = connect(tmp_path / "watchlist.db")
    try:
        initialize_database(conn)

        run = get_watchlist(conn, "2026-06-01")

        assert run["status"] == "not_generated"
        assert run["item_count"] == 0
        assert run["items"] == []
    finally:
        conn.close()
