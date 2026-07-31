from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

from .market_provider import MarketBar


INVALID_MINUTE_BAR = "invalid_minute_bar"
ISOLATED_PRICE_DISCONTINUITY = "isolated_price_discontinuity"
ISOLATED_PRICE_MOVE_RATIO = 0.05
NEIGHBOR_PRICE_MOVE_RATIO = 0.015
ISOLATED_RANGE_MULTIPLIER = 8.0
MIN_ISOLATED_CHECK_BARS = 5


def minute_bar_quality_issue(bars: Sequence[MarketBar | Mapping[str, Any]]) -> str | None:
    normalized: list[dict[str, float]] = []
    for bar in bars:
        values = _bar_values(bar)
        if values is None:
            return INVALID_MINUTE_BAR
        normalized.append(values)

    if len(normalized) < MIN_ISOLATED_CHECK_BARS:
        return None

    positive_ranges = [
        bar["high"] - bar["low"]
        for bar in normalized
        if bar["high"] > bar["low"]
    ]
    typical_range = median(positive_ranges) if positive_ranges else 0.0
    for index in range(1, len(normalized) - 1):
        previous_bar = normalized[index - 1]
        current_bar = normalized[index]
        next_bar = normalized[index + 1]
        reference_price = median(
            [
                previous_bar["close"],
                current_bar["open"],
                next_bar["open"],
                next_bar["close"],
            ]
        )
        if reference_price <= 0:
            continue

        neighbor_move_ratio = max(
            abs(previous_bar["close"] - next_bar["open"]),
            abs(previous_bar["close"] - next_bar["close"]),
        ) / reference_price
        isolated_move_ratio = max(
            abs(current_bar["high"] - reference_price),
            abs(current_bar["low"] - reference_price),
            abs(current_bar["close"] - reference_price),
        ) / reference_price
        current_range = current_bar["high"] - current_bar["low"]
        minimum_extreme_range = max(
            typical_range * ISOLATED_RANGE_MULTIPLIER,
            reference_price * (ISOLATED_PRICE_MOVE_RATIO / 2),
        )
        if (
            neighbor_move_ratio <= NEIGHBOR_PRICE_MOVE_RATIO
            and isolated_move_ratio >= ISOLATED_PRICE_MOVE_RATIO
            and current_range >= minimum_extreme_range
        ):
            return ISOLATED_PRICE_DISCONTINUITY
    return None


def archive_quality_projection(archive: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(archive)
    if str(payload.get("data_status", "")) not in {"available", "partial"}:
        return payload

    bars = payload.get("bars")
    if not isinstance(bars, list):
        try:
            decoded = json.loads(str(payload.get("bars_json", "[]")))
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = None
        bars = decoded if isinstance(decoded, list) else []
    payload["bars"] = bars
    issue = minute_bar_quality_issue(bars)
    if issue:
        payload["data_status"] = "partial"
        payload["failure_reason"] = issue
    return payload


def archive_preference_key(archive: Mapping[str, Any]) -> tuple[int, int]:
    status = str(archive.get("data_status", ""))
    provider = str(archive.get("provider", "")).lower()
    status_rank = {
        "available": 0,
        "partial": 1,
        "missing": 2,
        "timezone_conflict": 3,
        "provider_failed": 4,
    }.get(status, 5)
    if status in {"available", "partial"}:
        provider_rank = {"yahoo": 0, "futu": 1}.get(provider, 2)
    else:
        provider_rank = {"futu": 0, "yahoo": 1}.get(provider, 2)
    return status_rank, provider_rank


def _bar_values(bar: MarketBar | Mapping[str, Any]) -> dict[str, float] | None:
    raw = (
        {
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        if isinstance(bar, MarketBar)
        else bar
    )
    try:
        values = {
            "open": float(raw["open"]),
            "high": float(raw["high"]),
            "low": float(raw["low"]),
            "close": float(raw["close"]),
            "volume": float(raw.get("volume", 0.0)),
        }
    except (KeyError, TypeError, ValueError):
        return None
    prices = [values["open"], values["high"], values["low"], values["close"]]
    if (
        not all(math.isfinite(value) and value > 0 for value in prices)
        or not math.isfinite(values["volume"])
        or values["volume"] < 0
        or values["high"] < max(values["open"], values["close"], values["low"])
        or values["low"] > min(values["open"], values["close"], values["high"])
    ):
        return None
    return values
