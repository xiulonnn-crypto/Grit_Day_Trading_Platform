from __future__ import annotations

import os
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .market_provider import MarketBar, MinuteBarResponse, WatchlistCandidate, WatchlistProviderResponse


class FutuMarketDataProvider:
    name = "futu"

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        market_prefix: str | None = None,
        auto_start_opend: bool = False,
    ) -> None:
        self._host = host or os.getenv("FUTU_HOST", "127.0.0.1")
        self._port = int(port or os.getenv("FUTU_PORT", "11111"))
        self._market_prefix = (market_prefix or os.getenv("FUTU_DEFAULT_MARKET", "US")).upper()
        self._auto_start_opend = auto_start_opend

    def fetch_minute_bars(self, symbol: str, requested_start: str, requested_end: str) -> MinuteBarResponse:
        futu = _import_futu()
        if futu is None:
            return _failed_minute("futu_sdk_not_installed")
        code = self._normalize_code(symbol)
        quote_ctx = None
        try:
            quote_ctx = _open_quote_context(
                futu,
                host=self._host,
                port=self._port,
                auto_start_opend=self._auto_start_opend,
            )
            quota_error = _history_quota_error(quote_ctx, futu, code)
            if quota_error:
                return _failed_minute(quota_error)
            history_result = quote_ctx.request_history_kline(
                code,
                start=requested_start[:10],
                end=requested_end[:10],
                ktype=futu.KLType.K_1M,
                autype=futu.AuType.NONE,
                max_count=1000,
                extended_time=True,
            )
            ret, data = _result_pair(history_result)
            if ret != futu.RET_OK:
                return _failed_minute("futu_history_kline_failed")
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


def _open_quote_context(futu: Any, *, host: str, port: int, auto_start_opend: bool) -> Any:
    try:
        return futu.OpenQuoteContext(host=host, port=port)
    except Exception:
        if not auto_start_opend or not _start_futu_opend(host, port):
            raise
    return futu.OpenQuoteContext(host=host, port=port)


def _start_futu_opend(host: str, port: int) -> bool:
    if os.name != "nt" or host.strip().lower() not in {"127.0.0.1", "localhost"}:
        return False
    if os.getenv("FUTU_AUTO_START_OPEND", "1").strip().lower() in {"0", "false", "no", "off"}:
        return False
    appdata = os.getenv("APPDATA", "").strip()
    if not appdata:
        return False
    executable = Path(appdata) / "Futu_OpenD" / "Futu_OpenD.exe"
    if not executable.is_file():
        return False

    creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess,
        "DETACHED_PROCESS",
        0,
    )
    try:
        subprocess.Popen(
            [str(executable)],
            cwd=str(executable.parent),
            close_fds=True,
            creationflags=creation_flags,
        )
    except OSError:
        return False

    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if _port_is_listening(host, port):
            return True
        time.sleep(0.25)
    return False


def _port_is_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def _history_quota_error(quote_ctx: Any, futu: Any, code: str) -> str | None:
    get_quota = getattr(quote_ctx, "get_history_kl_quota", None)
    if not callable(get_quota):
        return "futu_history_quota_check_unavailable"
    quota_result = get_quota(get_detail=True)
    ret, data = _result_pair(quota_result)
    if ret != futu.RET_OK:
        return "futu_history_quota_check_failed"

    remaining = _quota_remaining(data)
    if remaining is None or remaining > 0:
        return None
    if code in _quota_codes(data):
        return None
    return "futu_history_quota_exhausted"


def _result_pair(result: Any) -> tuple[Any, Any]:
    if not isinstance(result, tuple) or len(result) < 2:
        return None, result
    return result[0], result[1]


def _quota_remaining(data: Any) -> int | None:
    if isinstance(data, dict):
        raw = data.get("remain_quota", data.get("remainQuota"))
        return _safe_int(raw)
    if isinstance(data, tuple) and len(data) >= 2:
        return _safe_int(data[1])
    return None


def _quota_codes(data: Any) -> set[str]:
    codes: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            raw_code = value.get("code")
            if raw_code:
                codes.add(str(raw_code).strip().upper())
            for nested in value.values():
                if isinstance(nested, (dict, list, tuple)):
                    visit(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                visit(nested)

    visit(data)
    return codes


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


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
