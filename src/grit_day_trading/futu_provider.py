from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from .market_provider import MarketBar, MinuteBarResponse, WatchlistCandidate, WatchlistProviderResponse


class FutuMarketDataProvider:
    name = "futu"

    def __init__(self, *, host: str | None = None, port: int | None = None, market_prefix: str | None = None) -> None:
        self._host = host or os.getenv("FUTU_HOST", "127.0.0.1")
        self._port = int(port or os.getenv("FUTU_PORT", "11111"))
        self._market_prefix = (market_prefix or os.getenv("FUTU_DEFAULT_MARKET", "US")).upper()

    def fetch_minute_bars(self, symbol: str, requested_start: str, requested_end: str) -> MinuteBarResponse:
        futu = _import_futu()
        if futu is None:
            return _failed_minute("futu_sdk_not_installed")
        code = self._normalize_code(symbol)
        quote_ctx = None
        try:
            quote_ctx = futu.OpenQuoteContext(host=self._host, port=self._port)
            ret, data = quote_ctx.request_history_kline(
                code,
                start=requested_start[:10],
                end=requested_end[:10],
                ktype=futu.KLType.K_1M,
                autype=futu.AuType.NONE,
                extended_time=True,
            )
            if ret != futu.RET_OK:
                return _failed_minute(str(data) or "futu_minute_bars_failed")
            bars = _bars_from_dataframe(data, requested_start, requested_end)
            if not bars:
                return MinuteBarResponse(status="missing", bars=[], provider_timezone="America/New_York")
            return MinuteBarResponse(status="available", bars=bars, provider_timezone="America/New_York")
        except Exception as exc:  # pragma: no cover - live adapter safety net
            return _failed_minute(f"futu_exception:{exc.__class__.__name__}")
        finally:
            if quote_ctx is not None:
                quote_ctx.close()

    def fetch_watchlist_candidates(self, trade_date: str) -> WatchlistProviderResponse:
        futu = _import_futu()
        if futu is None:
            return WatchlistProviderResponse(status="provider_failed", candidates=[], error_code="futu_sdk_not_installed")
        symbols = [item.strip() for item in os.getenv("FUTU_WATCHLIST_SYMBOLS", "").split(",") if item.strip()]
        if not symbols:
            return WatchlistProviderResponse(status="missing", candidates=[], error_code="futu_watchlist_symbols_not_configured")
        codes = [self._normalize_code(symbol) for symbol in symbols]
        quote_ctx = None
        try:
            quote_ctx = futu.OpenQuoteContext(host=self._host, port=self._port)
            ret, data = quote_ctx.get_market_snapshot(codes)
            if ret != futu.RET_OK:
                return WatchlistProviderResponse(status="provider_failed", candidates=[], error_code=str(data))
            candidates = [_candidate_from_snapshot(row) for _, row in data.iterrows()]
            return WatchlistProviderResponse(status="available", candidates=[item for item in candidates if item is not None])
        except Exception as exc:  # pragma: no cover - live adapter safety net
            return WatchlistProviderResponse(
                status="provider_failed",
                candidates=[],
                error_code=f"futu_exception:{exc.__class__.__name__}",
            )
        finally:
            if quote_ctx is not None:
                quote_ctx.close()

    def _normalize_code(self, symbol: str) -> str:
        value = symbol.strip().upper()
        if "." in value:
            return value
        return f"{self._market_prefix}.{value}"


def _import_futu():
    try:
        import futu  # type: ignore[import-not-found]
    except Exception:
        return None
    return futu


def _failed_minute(error_code: str) -> MinuteBarResponse:
    return MinuteBarResponse(
        status="provider_failed",
        bars=[],
        provider_timezone="America/New_York",
        error_code=error_code,
    )


def _bars_from_dataframe(data: Any, requested_start: str, requested_end: str) -> list[MarketBar]:
    bars: list[MarketBar] = []
    start = _parse_iso(requested_start)
    end = _parse_iso(requested_end)
    for _, row in data.iterrows():
        timestamp = _row_value(row, "time_key", "datetime", "time")
        if timestamp is None:
            continue
        parsed = _parse_iso(str(timestamp).replace(" ", "T"))
        if parsed < start or parsed > end:
            continue
        bars.append(
            MarketBar(
                timestamp=parsed.replace(microsecond=0).isoformat(),
                open=float(_row_value(row, "open") or 0.0),
                high=float(_row_value(row, "high") or 0.0),
                low=float(_row_value(row, "low") or 0.0),
                close=float(_row_value(row, "close") or 0.0),
                volume=float(_row_value(row, "volume") or 0.0),
            )
        )
    return bars


def _candidate_from_snapshot(row: Any) -> WatchlistCandidate | None:
    symbol = str(_row_value(row, "code") or "").strip().upper()
    if not symbol:
        return None
    last_price = _safe_float(_row_value(row, "last_price", "price"))
    prev_close = _safe_float(_row_value(row, "prev_close_price", "pre_close_price"))
    change_rate = _safe_float(_row_value(row, "change_rate"))
    volume = _safe_float(_row_value(row, "volume"))
    turnover_rate = _safe_float(_row_value(row, "turnover_rate"))
    gap_percent = 0.0 if not prev_close else ((last_price - prev_close) / prev_close) * 100
    metrics = {
        "relative_volume": max(0.0, turnover_rate),
        "gap_percent": gap_percent,
        "price_change_percent": change_rate,
        "volume": volume,
    }
    return WatchlistCandidate(symbol=symbol, metrics=metrics, source="futu_snapshot")


def _row_value(row: Any, *keys: str) -> Any:
    for key in keys:
        try:
            value = row[key]
        except Exception:
            continue
        if value is not None:
            return value
    return None


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
