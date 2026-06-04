from pathlib import Path

from fastapi.testclient import TestClient

from grit_day_trading import market_archive
from grit_day_trading.api import create_app
from grit_day_trading.market_provider import FakeMarketDataProvider, MarketBar


SAMPLE_PATH = Path("tests/fixtures/stp_sample.tsv")


def test_healthz_advertises_p1_runtime_routes(tmp_path):
    with TestClient(create_app(tmp_path / "healthz.db")) as client:
        health = client.get("/api/healthz")
        openapi = client.get("/openapi.json")

    assert health.status_code == 200
    payload = health.json()
    assert payload["status"] == "ok"
    assert "/api/market-data/minute-archives" in payload["required_routes"]
    assert "/api/market-data/yahoo-minute-archive" in payload["required_routes"]
    routes = openapi.json()["paths"]
    assert "/api/market-data/minute-archives" in routes
    assert "/api/market-data/yahoo-minute-archive" in routes


def test_market_context_api_replays_and_reads_snapshot(tmp_path):
    with TestClient(create_app(tmp_path / "p1.db")) as client:
        client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", SAMPLE_PATH.read_bytes(), "text/plain")})
        fill = client.get("/api/fills?date=2026-06-01").json()["items"][0]

        replay = client.post(
            "/api/market-context/replay",
            json={"fill_id": fill["fill_id"], "provider": "fake", "minutes_before": 1, "minutes_after": 1},
        )
        fill_context = client.get(f"/api/fills/{fill['fill_id']}/market-context")
        snapshot = client.get(f"/api/market-context/{replay.json()['snapshot_id']}")

    assert replay.status_code == 200
    payload = replay.json()
    assert payload["fill_id"] == fill["fill_id"]
    assert payload["provider"] == "fake"
    assert payload["data_status"] == "available"
    assert payload["bar_count"] == 3
    assert len(payload["bars_hash"]) == 64
    assert fill_context.status_code == 200
    assert fill_context.json()["snapshot_id"] == payload["snapshot_id"]
    assert snapshot.status_code == 200
    assert snapshot.json()["snapshot_id"] == payload["snapshot_id"]


def test_market_context_api_error_contracts(tmp_path):
    with TestClient(create_app(tmp_path / "p1.db")) as client:
        missing_fill = client.post(
            "/api/market-context/replay",
            json={"fill_id": "fill_missing", "provider": "fake", "minutes_before": 1, "minutes_after": 1},
        )
        invalid_window = client.post(
            "/api/market-context/replay",
            json={"fill_id": "fill_missing", "provider": "fake", "minutes_before": 0, "minutes_after": 1},
        )
        missing_snapshot = client.get("/api/market-context/mctx_missing")

    assert missing_fill.status_code == 404
    assert missing_fill.json() == {"detail": "fill_not_found"}
    assert invalid_window.status_code == 422
    assert missing_snapshot.status_code == 404
    assert missing_snapshot.json() == {"detail": "market_context_not_found"}


def test_market_context_api_force_replay_updates_existing_snapshot(tmp_path):
    with TestClient(create_app(tmp_path / "p1.db")) as client:
        client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", SAMPLE_PATH.read_bytes(), "text/plain")})
        fill = client.get("/api/fills?date=2026-06-01").json()["items"][0]
        first = client.post(
            "/api/market-context/replay",
            json={"fill_id": fill["fill_id"], "provider": "fake", "minutes_before": 1, "minutes_after": 1},
        ).json()
        forced = client.post(
            "/api/market-context/replay",
            json={
                "fill_id": fill["fill_id"],
                "provider": "fake",
                "minutes_before": 1,
                "minutes_after": 1,
                "force": True,
            },
        ).json()

    assert forced["snapshot_id"] == first["snapshot_id"]
    assert forced["bars_hash"] == first["bars_hash"]


def test_watchlist_api_generates_reads_and_validates_dates(tmp_path):
    with TestClient(create_app(tmp_path / "p1.db")) as client:
        empty = client.get("/api/watchlist?date=2026-06-01")
        generated = client.post("/api/watchlist/generate", json={"date": "2026-06-01", "provider": "fake"})
        listed = client.get("/api/watchlist?date=2026-06-01")
        rerun = client.put("/api/watchlist/2026-06-01", json={"provider": "fake", "force": True})
        invalid_get = client.get("/api/watchlist?date=20260601")
        invalid_post = client.post("/api/watchlist/generate", json={"date": "20260601", "provider": "fake"})

    assert empty.status_code == 200
    assert empty.json()["status"] == "not_generated"
    assert generated.status_code == 200
    assert generated.json()["status"] == "completed"
    assert generated.json()["item_count"] >= 1
    assert all(item["reason_codes"] for item in generated.json()["items"])
    assert all(item["metrics"] for item in generated.json()["items"])
    assert listed.status_code == 200
    assert listed.json()["run_id"] == generated.json()["run_id"]
    assert rerun.status_code == 200
    assert rerun.json()["run_id"] == generated.json()["run_id"]
    assert invalid_get.status_code == 422
    assert invalid_post.status_code == 422


def test_yahoo_minute_archive_api_archives_and_lists_committed_fill_symbols(tmp_path, monkeypatch):
    provider = FakeMarketDataProvider(
        minute_bars={
            "AAPL": [
                MarketBar("2026-06-01T09:30:00", 99.5, 101.0, 99.0, 100.0, 100),
                MarketBar("2026-06-01T09:31:00", 100.5, 103.0, 100.0, 102.0, 300),
            ]
        }
    )
    monkeypatch.setattr(market_archive, "resolve_provider", lambda provider_name: provider)

    with TestClient(create_app(tmp_path / "p1-archive.db")) as client:
        client.post("/api/imports/stp-txt", files={"file": ("sample.tsv", SAMPLE_PATH.read_bytes(), "text/plain")})
        archived = client.post("/api/market-data/yahoo-minute-archive", json={"date": "2026-06-01"})
        listed = client.get("/api/market-data/minute-archives?date=2026-06-01&provider=yahoo")

    assert archived.status_code == 200
    payload = archived.json()
    assert payload["provider"] == "yahoo"
    assert payload["target_count"] == 1
    assert payload["items"][0]["symbol"] == "AAPL"
    assert payload["items"][0]["source_fill_count"] == 2
    assert payload["items"][0]["data_status"] == "available"
    assert listed.status_code == 200
    assert listed.json()["items"][0]["archive_id"] == payload["items"][0]["archive_id"]


def test_yahoo_minute_archive_api_archives_manual_symbol_window(tmp_path, monkeypatch):
    provider = FakeMarketDataProvider()
    monkeypatch.setattr(market_archive, "resolve_provider", lambda provider_name: provider)

    with TestClient(create_app(tmp_path / "p1-archive-symbol.db")) as client:
        archived = client.post(
            "/api/market-data/yahoo-minute-archive",
            json={"date": "2026-06-05", "symbol": "msft", "window_trading_days": 3},
        )
        listed = client.get("/api/market-data/minute-archives?symbol=MSFT&provider=yahoo")

    assert archived.status_code == 200
    payload = archived.json()
    assert payload["symbol"] == "MSFT"
    assert payload["requested_trade_dates"] == ["2026-06-03", "2026-06-04", "2026-06-05"]
    assert payload["target_count"] == 3
    assert payload["selected_symbol_available_count"] == 3
    assert [item["symbol"] for item in listed.json()["items"]] == ["MSFT", "MSFT", "MSFT"]


def test_yahoo_minute_archive_api_rejects_window_without_symbol(tmp_path):
    with TestClient(create_app(tmp_path / "p1-archive-invalid.db")) as client:
        response = client.post(
            "/api/market-data/yahoo-minute-archive",
            json={"date": "2026-06-05", "window_trading_days": 3},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "archive_symbol_required"
