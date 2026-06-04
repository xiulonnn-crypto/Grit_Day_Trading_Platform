from datetime import datetime
from zoneinfo import ZoneInfo

from grit_day_trading.yahoo_provider import YahooFinanceMarketDataProvider


def test_yahoo_provider_maps_chart_payload_to_minute_bars():
    captured: dict[str, str | float] = {}

    def fetch_json(url: str, timeout_seconds: float):
        captured["url"] = url
        captured["timeout"] = timeout_seconds
        return _chart_payload(
            [
                _epoch("2026-06-01T09:30:00"),
                _epoch("2026-06-01T09:31:00"),
            ]
        )

    provider = YahooFinanceMarketDataProvider(fetch_json=fetch_json, timeout_seconds=3)

    response = provider.fetch_minute_bars("US.AAPL", "2026-06-01T09:30:00", "2026-06-01T09:31:00")

    assert response.status == "available"
    assert response.provider_timezone == "America/New_York"
    assert captured["timeout"] == 3
    assert "/AAPL?" in str(captured["url"])
    assert "interval=1m" in str(captured["url"])
    assert "includePrePost=true" in str(captured["url"])
    assert [bar.timestamp for bar in response.bars] == ["2026-06-01T09:30:00", "2026-06-01T09:31:00"]
    assert response.bars[0].open == 100.0
    assert response.bars[1].volume == 2000.0


def test_yahoo_provider_returns_missing_when_chart_has_no_usable_bars():
    provider = YahooFinanceMarketDataProvider(fetch_json=lambda url, timeout: _chart_payload([]))

    response = provider.fetch_minute_bars("AAPL", "2026-06-01T09:30:00", "2026-06-01T09:31:00")

    assert response.status == "missing"
    assert response.bars == []


def test_yahoo_provider_surfaces_chart_errors_as_provider_failed():
    provider = YahooFinanceMarketDataProvider(
        fetch_json=lambda url, timeout: {"chart": {"result": None, "error": {"code": "Not Found"}}}
    )

    response = provider.fetch_minute_bars("AAPL", "2026-06-01T09:30:00", "2026-06-01T09:31:00")

    assert response.status == "provider_failed"
    assert response.error_code == "yahoo_chart_error:Not Found"


def _chart_payload(timestamps: list[int]):
    return {
        "chart": {
            "result": [
                {
                    "meta": {"exchangeTimezoneName": "America/New_York"},
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, 101.0][: len(timestamps)],
                                "high": [101.0, 102.0][: len(timestamps)],
                                "low": [99.5, 100.5][: len(timestamps)],
                                "close": [100.5, 101.5][: len(timestamps)],
                                "volume": [1000, 2000][: len(timestamps)],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def _epoch(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=ZoneInfo("America/New_York")).timestamp())
