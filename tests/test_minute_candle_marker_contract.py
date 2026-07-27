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


def _candle_fill_price_summary_source() -> str:
    start = APP_SOURCE.index("function formatCandleFillPriceSummary")
    end = APP_SOURCE.index("\n\nfunction MinuteCandleChart", start)
    return APP_SOURCE[start:end]


def test_trade_marker_glyph_tip_uses_execution_price_anchor():
    source = _trade_marker_path_source()

    assert "return `M ${x} ${y} L ${x - size} ${y + size * 2} L ${x + size} ${y + size * 2} Z`;" in source
    assert "return `M ${x} ${y} L ${x - size} ${y - size * 2} L ${x + size} ${y - size * 2} Z`;" in source
    assert "M ${x} ${y - size}" not in source
    assert "M ${x} ${y + size}" not in source


def test_trade_markers_still_use_bar_time_and_execution_price_coordinates():
    assert "const index = nearestBarIndex(fill.filled_at, bars);" in APP_SOURCE
    assert "const fillMarkerAnchors = showTradeMarkers" in APP_SOURCE
    assert "const markers = fillMarkerAnchors.map(({ fill, index }) => ({" in APP_SOURCE
    assert "x: xForIndex(index)," in APP_SOURCE
    assert "y: yForPrice(fill.price)" in APP_SOURCE
    assert '<circle cx={x} cy={y} r="2.4" />' in APP_SOURCE


def test_candle_chart_y_axis_uses_execution_prices_not_risk_targets():
    source = _minute_candle_chart_source()
    domain_start = source.index("const primaryPriceValues")
    domain_end = source.index("const priceDomain = chartPriceDomain", domain_start)
    domain_source = source[domain_start:domain_end]

    assert "const visibleFillPrices = fillMarkerAnchors.map(({ fill }) => fill.price);" in source
    assert "const visibleStrategySignalPrices = strategyMarkerAnchors.map(({ signal }) => signal.price);" in source
    assert "const primaryPriceValues = stableChartPrimaryPrices(bars, [...visibleFillPrices, ...visibleStrategySignalPrices]);" in source
    assert "nearbyChartOverlayPrices(primaryPriceValues, auxiliaryPriceValues)" in domain_source
    assert "signal.stop_loss_price" not in domain_source
    assert "signal.take_profit_price" not in domain_source
    assert "isPriceVisible(props.archive.vwap)" in source
    assert 'indicatorLinePath(strategyLinePoints, "bb_lower", xForIndex, yForPrice, isPriceVisible)' in source


def test_candle_chart_does_not_snap_out_of_window_markers_to_edge_bars():
    source = _minute_candle_chart_source()
    nearest_source = APP_SOURCE[
        APP_SOURCE.index("function nearestBarIndex"):
        APP_SOURCE.index("\n\nfunction isFiniteNumber", APP_SOURCE.index("function nearestBarIndex"))
    ]

    assert "const maxMarkerBarDistanceMinutes = 1;" in nearest_source
    assert "return bestDistance <= maxMarkerBarDistanceMinutes ? bestIndex : -1;" in nearest_source
    assert "const fillMarkerAnchors = showTradeMarkers" in source
    assert "return index < 0 ? null : { fill, index };" in source
    assert "const strategyMarkerAnchors = visibleStrategySignals" in source
    assert "return index < 0 ? null : { signal, index };" in source
    assert "0 / ${formatInteger(props.fills.length)} 个可见成交标记" not in source
    assert "${formatInteger(markers.length)} / ${formatInteger(props.fills.length)} 个可见成交标记" in source


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
    assert "const tradeReplayHalfHourWindowMinutes = 30;" in APP_SOURCE
    assert "chartMinuteScope(props.fills, visibleStrategySignals, minuteCandleEdgeBufferBars)" in source
    assert "const visibleScope = scopedBars.length > 0 ? fillScope : null;" in source
    assert "const scopeStartLabel = visibleScope ? formatMinuteOfDay(visibleScope.startMinute)" in source
    assert "const scopeEndLabel = visibleScope" in source
    assert "showHalfHourReplayWindow ? tradeReplayHalfHourWindowMinutes : minuteCandleEdgeBufferBars" in APP_SOURCE
    assert "scope={replayScope}" in APP_SOURCE
    assert "function chartMinuteScope(fills: ChartFill[], signals: StrategySignal[], bufferMinutes = 0)" in APP_SOURCE
    assert "startMinute: Math.max(0, Math.min(...minutes) - bufferMinutes)" in APP_SOURCE
    assert "endMinute: Math.min(24 * 60 - 1, Math.max(...minutes) + bufferMinutes)" in APP_SOURCE
    assert "<span>查看半小时</span>" in APP_SOURCE
    assert 'title="开平仓前后各半小时"' in APP_SOURCE
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


def test_shared_candle_chart_shows_hovered_archive_bar_ohlc():
    source = _minute_candle_chart_source()

    assert "const [hoveredBarIndex, setHoveredBarIndex] = useState<number | null>(null);" in source
    assert "const handleCandlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {" in source
    assert "onPointerMove={handleCandlePointerMove}" in source
    assert 'className="candleOhlcTooltip"' in source
    assert "{formatClock(hoveredBar.timestamp)} · 分钟行情" in source
    assert "开盘价 {decimalFormatter.format(hoveredBar.open)}" in source
    assert "最高价 {decimalFormatter.format(hoveredBar.high)}" in source
    assert "最低价 {decimalFormatter.format(hoveredBar.low)}" in source
    assert "收盘价 {decimalFormatter.format(hoveredBar.close)}" in source
    assert "VWAP价 {hoveredVwapPriceLabel}" in source
    assert 'props.archive.vwap == null ? "—" : decimalFormatter.format(props.archive.vwap)' in source
    assert 'VWAP价 ${props.archive.vwap == null ? "暂无" : hoveredVwapPriceLabel}' in source


def test_candle_hover_uses_committed_fill_prices_for_the_hovered_bar():
    source = _minute_candle_chart_source()
    summary_source = _candle_fill_price_summary_source()

    assert (
        "const hoveredBarFills = hoveredBarIndex === null\n"
        "    ? []\n"
        "    : fillMarkerAnchors.filter(({ index }) => index === hoveredBarIndex).map(({ fill }) => fill);"
    ) in source
    assert 'const hoveredBuyFills = hoveredBarFills.filter((fill) => fill.side === "BUY");' in source
    assert 'const hoveredSellFills = hoveredBarFills.filter((fill) => fill.side === "SELL");' in source
    assert "const hoveredBuyPriceLabel = formatCandleFillPriceSummary(hoveredBuyFills);" in source
    assert "const hoveredSellPriceLabel = formatCandleFillPriceSummary(hoveredSellFills);" in source
    assert "买入价 {hoveredBuyPriceLabel}" in source
    assert "卖出价 {hoveredSellPriceLabel}" in source
    assert '买入价 ${hoveredBuyFills.length === 0 ? "暂无" : hoveredBuyPriceLabel}' in source
    assert '卖出价 ${hoveredSellFills.length === 0 ? "暂无" : hoveredSellPriceLabel}' in source
    assert 'if (fills.length === 0) return "—";' in summary_source
    assert ".sort((left, right) => left - right);" in summary_source
    assert "minPrice === maxPrice" in summary_source
    assert "`${decimalFormatter.format(minPrice)}–${decimalFormatter.format(maxPrice)}`" in summary_source
    assert "`${priceLabel} · ${formatInteger(prices.length)}笔`" in summary_source
    assert "reduce(" not in summary_source


def test_candle_hover_clears_outside_plot_and_when_archive_scope_changes():
    source = _minute_candle_chart_source()

    assert "pointerY > priceBottom" in source
    assert 'className="chartShell"' in source
    assert "onMouseLeave={() => setHoveredBarIndex(null)}" in source
    assert "onPointerLeave={() => setHoveredBarIndex(null)}" in source
    assert "onPointerCancel={() => setHoveredBarIndex(null)}" in source
    assert 'window.addEventListener("pointermove", clearHoveredBarOutsideChart, true);' in source
    assert 'window.removeEventListener("pointermove", clearHoveredBarOutsideChart, true);' in source
    assert "!chartShell.contains(event.target as Node)" in source
    assert "setHoveredBarIndex(null);" in source
    assert "[props.archive.bars_hash, visibleScope?.startMinute, visibleScope?.endMinute]" in source
    assert "hoveredBarIndex === null ? null : bars[hoveredBarIndex] ?? null" in source
