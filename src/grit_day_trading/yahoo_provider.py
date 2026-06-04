from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .market_provider import MarketBar, MinuteBarResponse, WatchlistProviderResponse


JsonFetcher = Callable[[str, float], dict[str, Any]]


class YahooFinanceMarketDataProvider:
    name = "yahoo"

    def __init__(
        self,
        *,
        timeout_seconds: float | None = None,
        fetch_json: JsonFetcher | None = None,
        provider_timezone: str = "America/New_York",
    ) -> None:
        self._timeout_seconds = float(timeout_seconds or os.getenv("YAHOO_HTTP_TIMEOUT_SECONDS", "10"))
        self._fetch_json = fetch_json or _fetch_json
        self._provider_timezone = provider_timezone

    def fetch_minute_bars(self, symbol: str, requested_start: str, requested_end: str) -> MinuteBarResponse:
        yahoo_symbol = _normalize_yahoo_symbol(symbol)
        if not yahoo_symbol:
            return _failed_minute("yahoo_symbol_required", self._provider_timezone)

        try:
            start_epoch = _to_epoch(requested_start, self._provider_timezone)
            end_epoch = _to_epoch(requested_end, self._provider_timezone)
        except ValueError:
            return _failed_minute("yahoo_invalid_time_window", self._provider_timezone)
        if end_epoch <= start_epoch:
            return _failed_minute("yahoo_invalid_time_window", self._provider_timezone)

        url = _chart_url(yahoo_symbol, start_epoch, end_epoch)
        try:
            payload = self._fetch_json(url, self._timeout_seconds)
            result = _chart_result(payload)
            provider_timezone = _provider_timezone(result) or self._provider_timezone
            bars = _bars_from_result(result, requested_start, requested_end, provider_timezone)
        except YahooChartError as exc:
            return _failed_minute(exc.error_code, self._provider_timezone)
        except Exception as exc:  # pragma: no cover - live adapter safety net
            return _failed_minute(f"yahoo_exception:{exc.__class__.__name__}", self._provider_timezone)

        if not bars:
            return MinuteBarResponse(status="missing", bars=[], provider_timezone=provider_timezone)
        return MinuteBarResponse(status="available", bars=bars, provider_timezone=provider_timezone)

    def fetch_watchlist_candidates(self, trade_date: str) -> WatchlistProviderResponse:
        return WatchlistProviderResponse(
            status="provider_failed",
            candidates=[],
            error_code="yahoo_watchlist_not_supported",
        )


class YahooChartError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


def _fetch_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "GritDayTradingPlatform/0.1 market-data-archive",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise YahooChartError(f"yahoo_http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        reason = exc.reason.__class__.__name__ if hasattr(exc, "reason") else "url_error"
        raise YahooChartError(f"yahoo_url_error:{reason}") from exc
    except json.JSONDecodeError as exc:
        raise YahooChartError("yahoo_invalid_json") from exc


def _chart_url(symbol: str, start_epoch: int, end_epoch: int) -> str:
    encoded_symbol = urllib.parse.quote(symbol, safe="")
    query = urllib.parse.urlencode(
        {
            "period1": start_epoch,
            "period2": end_epoch,
            "interval": "1m",
            "includePrePost": "true",
            "events": "div,splits",
        }
    )
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?{query}"


def _chart_result(payload: dict[str, Any]) -> dict[str, Any]:
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise YahooChartError("yahoo_chart_missing")
    error = chart.get("error")
    if error:
        code = "yahoo_chart_error"
        if isinstance(error, dict) and error.get("code"):
            code = f"yahoo_chart_error:{error['code']}"
        raise YahooChartError(code)
    results = chart.get("result")
    if not isinstance(results, list) or not results:
        raise YahooChartError("yahoo_result_missing")
    result = results[0]
    if not isinstance(result, dict):
        raise YahooChartError("yahoo_result_invalid")
    return result


def _provider_timezone(result: dict[str, Any]) -> str | None:
    meta = result.get("meta")
    if not isinstance(meta, dict):
        return None
    timezone = meta.get("timezone")
    if isinstance(timezone, str) and "/" in timezone:
        return timezone
    exchange_timezone = meta.get("exchangeTimezoneName")
    if isinstance(exchange_timezone, str) and exchange_timezone:
        return exchange_timezone
    return None


def _bars_from_result(
    result: dict[str, Any],
    requested_start: str,
    requested_end: str,
    provider_timezone: str,
) -> list[MarketBar]:
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    if not isinstance(timestamps, list) or not isinstance(quote, dict):
        return []

    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    start = _parse_local(requested_start, provider_timezone).replace(tzinfo=None)
    end = _parse_local(requested_end, provider_timezone).replace(tzinfo=None)
    tz = ZoneInfo(provider_timezone)

    bars: list[MarketBar] = []
    for index, raw_timestamp in enumerate(timestamps):
        open_value = _list_value(opens, index)
        high_value = _list_value(highs, index)
        low_value = _list_value(lows, index)
        close_value = _list_value(closes, index)
        if None in (open_value, high_value, low_value, close_value):
            continue
        local_time = datetime.fromtimestamp(int(raw_timestamp), tz).replace(tzinfo=None, microsecond=0)
        if local_time < start or local_time > end:
            continue
        bars.append(
            MarketBar(
                timestamp=local_time.isoformat(),
                open=float(open_value),
                high=float(high_value),
                low=float(low_value),
                close=float(close_value),
                volume=float(_list_value(volumes, index) or 0.0),
            )
        )
    return sorted(bars, key=lambda bar: bar.timestamp)


def _normalize_yahoo_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if value.startswith("US."):
        value = value[3:]
    if value.endswith(".US"):
        value = value[:-3]
    if "." in value:
        value = value.replace(".", "-")
    return value


def _to_epoch(value: str, provider_timezone: str) -> int:
    return int(_parse_local(value, provider_timezone).timestamp())


def _parse_local(value: str, provider_timezone: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    timezone = ZoneInfo(provider_timezone)
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone)
    return parsed.replace(tzinfo=timezone)


def _list_value(values: Any, index: int) -> Any:
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _failed_minute(error_code: str, provider_timezone: str) -> MinuteBarResponse:
    return MinuteBarResponse(
        status="provider_failed",
        bars=[],
        provider_timezone=provider_timezone,
        error_code=error_code,
    )
