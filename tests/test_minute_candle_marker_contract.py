from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")


def _trade_marker_path_source() -> str:
    start = APP_SOURCE.index("function tradeMarkerPath")
    end = APP_SOURCE.index("\n\nfunction indicatorLinePath", start)
    return APP_SOURCE[start:end]


def _minute_candle_chart_source() -> str:
    start = APP_SOURCE.index("function MinuteCandleChart")
    end = APP_SOURCE.index("\n\nfunction StrategySignalDetailModal", start)
    return APP_SOURCE[start:end]


def test_trade_marker_glyph_tip_uses_execution_price_anchor():
    source = _trade_marker_path_source()

    assert "return `M ${x} ${y} L ${x - size} ${y + size * 2} L ${x + size} ${y + size * 2} Z`;" in source
    assert "return `M ${x} ${y} L ${x - size} ${y - size * 2} L ${x + size} ${y - size * 2} Z`;" in source
    assert "M ${x} ${y - size}" not in source
    assert "M ${x} ${y + size}" not in source


def test_trade_markers_still_use_bar_time_and_execution_price_coordinates():
    assert "const index = nearestBarIndex(fill.filled_at, bars);" in APP_SOURCE
    assert "x: xForIndex(index), y: yForPrice(fill.price)" in APP_SOURCE
    assert '<circle cx={x} cy={y} r="2.4" />' in APP_SOURCE


def test_candle_chart_y_axis_uses_execution_prices_not_risk_targets():
    source = _minute_candle_chart_source()
    domain_start = source.index("const primaryPriceValues")
    domain_end = source.index("const priceDomain = chartPriceDomain", domain_start)
    domain_source = source[domain_start:domain_end]

    assert "const strategySignalExecutionPrices = visibleStrategySignals.map((signal) => signal.price);" in source
    assert "const primaryPriceValues = stableChartPrimaryPrices(bars, [...fillPrices, ...strategySignalExecutionPrices]);" in source
    assert "nearbyChartOverlayPrices(primaryPriceValues, auxiliaryPriceValues)" in domain_source
    assert "signal.stop_loss_price" not in domain_source
    assert "signal.take_profit_price" not in domain_source
    assert "isPriceVisible(props.archive.vwap)" in source
    assert 'indicatorLinePath(strategyLinePoints, "bb_lower", xForIndex, yForPrice, isPriceVisible)' in source


def test_candle_chart_y_axis_filters_isolated_wick_outliers_and_clips_price_plot():
    source = _minute_candle_chart_source()
    stable_source = APP_SOURCE[
        APP_SOURCE.index("function stableChartPrimaryPrices"):
        APP_SOURCE.index("\n\nfunction nearbyChartOverlayPrices")
    ]

    assert '<clipPath id={priceClipId}>' in source
    assert '<g clipPath={`url(#${priceClipId})`}>' in source
    assert "...bars.flatMap((bar) => [bar.open, bar.close])" in stable_source
    assert "const wickValues = finitePriceValues(bars.flatMap((bar) => [bar.high, bar.low]));" in stable_source
    assert "nearbyChartOverlayPrices(bodyAndMarkerValues, wickValues)" in stable_source


def test_candle_chart_default_scope_uses_same_ten_bar_buffer_as_trade_replay():
    source = _minute_candle_chart_source()

    assert "const minuteCandleEdgeBufferBars = 10;" in APP_SOURCE
    assert "chartMinuteScope(props.fills, visibleStrategySignals, minuteCandleEdgeBufferBars)" in source
    assert "tradeGroupScope(props.group, minuteCandleEdgeBufferBars)" in APP_SOURCE
    assert "function chartMinuteScope(fills: ChartFill[], signals: StrategySignal[], bufferMinutes = 0)" in APP_SOURCE
    assert "startMinute: Math.max(0, Math.min(...minutes) - bufferMinutes)" in APP_SOURCE
    assert "endMinute: Math.min(24 * 60 - 1, Math.max(...minutes) + bufferMinutes)" in APP_SOURCE
    assert "edgePaddingBars" not in source


def test_trade_replay_chart_adds_replay_only_ema20_overlay():
    source = _minute_candle_chart_source()
    replay_start = APP_SOURCE.index("function TradeReplayModal")
    replay_end = APP_SOURCE.index("\n\nfunction TradeReplayDrawdownEvidence", replay_start)
    replay_source = APP_SOURCE[replay_start:replay_end]

    assert "showReplayEma20?: boolean" in source
    assert "buildEma20OverlayPoints(allBars, bars)" in source
    assert "const replayEma20Values = replayEma20Points.map((point) => point.value);" in source
    assert "...replayEma20Values" in source
    assert '<path className="replayEma20Line" d={priceLinePath(replayEma20Points, xForIndex, yForPrice, isPriceVisible)} />' in source
    assert '<span className="legendItem replayEma">EMA20</span>' in source
    assert "showReplayEma20" in replay_source
    assert "function buildEma20OverlayPoints" in APP_SOURCE
    assert "function priceLinePath" in APP_SOURCE
