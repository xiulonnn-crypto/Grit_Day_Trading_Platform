from grit_day_trading.market_provider import MarketBar
from grit_day_trading.market_quality import (
    INVALID_MINUTE_BAR,
    ISOLATED_PRICE_DISCONTINUITY,
    archive_quality_projection,
    minute_bar_quality_issue,
)


def test_minute_bar_quality_detects_mu_isolated_price_discontinuity():
    bars = [
        MarketBar("2026-07-16T12:24:00", 847.89, 851.50, 847.64, 851.00, 135613),
        MarketBar("2026-07-16T12:25:00", 850.86, 851.04, 848.39, 850.85, 77545),
        MarketBar("2026-07-16T12:26:00", 850.92, 852.90, 850.57, 850.93, 88368),
        MarketBar("2026-07-16T12:27:00", 850.73, 904.28, 850.69, 904.28, 114391),
        MarketBar("2026-07-16T12:28:00", 850.51, 850.89, 849.62, 849.85, 44659),
        MarketBar("2026-07-16T12:29:00", 850.22, 850.22, 847.52, 849.58, 52312),
    ]

    assert minute_bar_quality_issue(bars) == ISOLATED_PRICE_DISCONTINUITY


def test_minute_bar_quality_keeps_sustained_price_move_available():
    bars = [
        MarketBar("2026-07-16T12:24:00", 100.0, 100.3, 99.8, 100.1, 1000),
        MarketBar("2026-07-16T12:25:00", 100.1, 100.5, 100.0, 100.4, 1200),
        MarketBar("2026-07-16T12:26:00", 100.4, 106.5, 100.3, 106.0, 5000),
        MarketBar("2026-07-16T12:27:00", 106.0, 107.0, 105.5, 106.6, 4500),
        MarketBar("2026-07-16T12:28:00", 106.6, 107.2, 106.2, 106.9, 3200),
    ]

    assert minute_bar_quality_issue(bars) is None


def test_archive_quality_projection_reclassifies_legacy_available_archive():
    projected = archive_quality_projection(
        {
            "provider": "yahoo",
            "data_status": "available",
            "failure_reason": None,
            "bars": [
                {"open": 100.0, "high": 100.3, "low": 99.8, "close": 100.1, "volume": 1000},
                {"open": 100.1, "high": 100.4, "low": 99.9, "close": 100.2, "volume": 1200},
                {"open": 100.2, "high": 107.0, "low": 100.1, "close": 107.0, "volume": 5000},
                {"open": 100.1, "high": 100.3, "low": 99.8, "close": 100.0, "volume": 1300},
                {"open": 100.0, "high": 100.2, "low": 99.7, "close": 99.9, "volume": 1100},
            ],
        }
    )

    assert projected["data_status"] == "partial"
    assert projected["failure_reason"] == ISOLATED_PRICE_DISCONTINUITY


def test_minute_bar_quality_rejects_invalid_ohlc():
    bars = [
        MarketBar("2026-07-16T12:24:00", 100.0, 99.0, 98.0, 100.0, 1000),
    ]

    assert minute_bar_quality_issue(bars) == INVALID_MINUTE_BAR
