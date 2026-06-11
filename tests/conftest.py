import pytest

from grit_day_trading import market_archive
from grit_day_trading.market_provider import FakeMarketDataProvider, MinuteBarResponse


class MissingMinuteArchiveProvider(FakeMarketDataProvider):
    def fetch_minute_bars(self, symbol: str, requested_start: str, requested_end: str) -> MinuteBarResponse:
        return MinuteBarResponse(status="missing", bars=[], provider_timezone="America/New_York")


@pytest.fixture(autouse=True)
def _default_fake_yahoo_archive_provider(monkeypatch):
    monkeypatch.setattr(market_archive, "resolve_provider", lambda provider_name: MissingMinuteArchiveProvider())
