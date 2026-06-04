from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol


MARKET_DATA_STATUSES = {"available", "partial", "missing", "provider_failed", "timezone_conflict"}


@dataclass(frozen=True)
class MarketBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def as_dict(self) -> dict[str, float | str]:
        return {
            "timestamp": self.timestamp,
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": float(self.volume),
        }


@dataclass(frozen=True)
class MinuteBarResponse:
    status: str
    bars: list[MarketBar]
    provider_timezone: str = "America/New_York"
    error_code: str | None = None


@dataclass(frozen=True)
class WatchlistCandidate:
    symbol: str
    metrics: dict[str, float]
    source: str = "provider_summary"
    status: str = "included"


@dataclass(frozen=True)
class WatchlistProviderResponse:
    status: str
    candidates: list[WatchlistCandidate]
    error_code: str | None = None


class MarketDataProvider(Protocol):
    name: str

    def fetch_minute_bars(self, symbol: str, requested_start: str, requested_end: str) -> MinuteBarResponse:
        ...

    def fetch_watchlist_candidates(self, trade_date: str) -> WatchlistProviderResponse:
        ...


class FakeMarketDataProvider:
    name = "fake"

    def __init__(
        self,
        *,
        minute_bars: dict[str, list[MarketBar | dict[str, float | str]]] | None = None,
        minute_status: dict[str, str] | None = None,
        watchlist_candidates: list[WatchlistCandidate | dict[str, object]] | None = None,
        watchlist_status: str = "available",
        provider_timezone: str = "America/New_York",
    ) -> None:
        self._minute_bars = {
            symbol.upper(): [_coerce_bar(bar) for bar in bars] for symbol, bars in (minute_bars or {}).items()
        }
        self._minute_status = {symbol.upper(): status for symbol, status in (minute_status or {}).items()}
        candidate_source = _default_candidates() if watchlist_candidates is None else watchlist_candidates
        self._watchlist_candidates = [_coerce_candidate(item) for item in candidate_source]
        self._watchlist_status = watchlist_status
        self._provider_timezone = provider_timezone

    def fetch_minute_bars(self, symbol: str, requested_start: str, requested_end: str) -> MinuteBarResponse:
        canonical_symbol = symbol.strip().upper()
        status = self._minute_status.get(canonical_symbol, "available")
        if status not in MARKET_DATA_STATUSES:
            status = "provider_failed"
        if status == "provider_failed":
            return MinuteBarResponse(
                status="provider_failed",
                bars=[],
                provider_timezone=self._provider_timezone,
                error_code="fake_provider_failed",
            )
        if status in {"missing", "timezone_conflict"}:
            return MinuteBarResponse(status=status, bars=[], provider_timezone=self._provider_timezone)

        bars = self._minute_bars.get(canonical_symbol)
        if bars is None:
            bars = _generate_bars(requested_start, requested_end, canonical_symbol)
        if status == "partial":
            bars = bars[: max(1, len(bars) // 2)]
        return MinuteBarResponse(status=status, bars=bars, provider_timezone=self._provider_timezone)

    def fetch_watchlist_candidates(self, trade_date: str) -> WatchlistProviderResponse:
        if self._watchlist_status == "provider_failed":
            return WatchlistProviderResponse(
                status="provider_failed",
                candidates=[],
                error_code="fake_watchlist_provider_failed",
            )
        if self._watchlist_status == "missing":
            return WatchlistProviderResponse(status="missing", candidates=[])
        return WatchlistProviderResponse(status=self._watchlist_status, candidates=self._watchlist_candidates)


def _coerce_bar(bar: MarketBar | dict[str, float | str]) -> MarketBar:
    if isinstance(bar, MarketBar):
        return bar
    return MarketBar(
        timestamp=str(bar["timestamp"]),
        open=float(bar["open"]),
        high=float(bar["high"]),
        low=float(bar["low"]),
        close=float(bar["close"]),
        volume=float(bar["volume"]),
    )


def _coerce_candidate(candidate: WatchlistCandidate | dict[str, object]) -> WatchlistCandidate:
    if isinstance(candidate, WatchlistCandidate):
        return candidate
    metrics = candidate.get("metrics", {})
    return WatchlistCandidate(
        symbol=str(candidate["symbol"]).strip().upper(),
        metrics={key: float(value) for key, value in dict(metrics).items()},
        source=str(candidate.get("source", "provider_summary")),
        status=str(candidate.get("status", "included")),
    )


def _generate_bars(requested_start: str, requested_end: str, symbol: str) -> list[MarketBar]:
    start = _parse_iso(requested_start)
    end = _parse_iso(requested_end)
    seed = sum(ord(char) for char in symbol) % 17
    base = 95.0 + seed
    bars: list[MarketBar] = []
    current = start
    index = 0
    while current <= end:
        close = base + index * 0.1
        bars.append(
            MarketBar(
                timestamp=_format_iso(current),
                open=round(close - 0.05, 4),
                high=round(close + 0.2, 4),
                low=round(close - 0.25, 4),
                close=round(close, 4),
                volume=1000 + index * 25,
            )
        )
        current += timedelta(minutes=1)
        index += 1
    return bars


def _default_candidates() -> list[WatchlistCandidate]:
    return [
        WatchlistCandidate(
            symbol="NVDA",
            metrics={"relative_volume": 2.4, "gap_percent": 3.1, "price_change_percent": 4.2},
        ),
        WatchlistCandidate(
            symbol="MSFT",
            metrics={"relative_volume": 1.7, "gap_percent": 1.2, "price_change_percent": 3.4},
        ),
        WatchlistCandidate(
            symbol="AAPL",
            metrics={"relative_volume": 1.2, "gap_percent": 0.4, "price_change_percent": 1.1},
        ),
    ]


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _format_iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()
